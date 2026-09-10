import json
import inspect
import time
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, ValidationError

from .models import (
    ChatReply,
    Diagnosis,
    ExtractedQuestions,
    GeneratedQuestion,
    ReferenceExtraction,
    Solution,
    Verification,
    validate_choice_answer,
)
from .prompts import (
    chat_prompt,
    diagnosis_prompt,
    extraction_prompt,
    generation_prompt,
    reference_extraction_prompt,
    solve_prompt,
    verification_prompt,
)


class ProviderError(RuntimeError):
    """A provider failure safe to display to a local user."""


# Whole-page transcription needs thousands of tokens; provider defaults cap far too low.
TASK_LIMITS = {
    "vision": {"max_tokens": 16384, "timeout": 420.0},
    "default": {"max_tokens": 8192, "timeout": 180.0},
}


class ModelGateway:
    def __init__(self, settings: Dict[str, Any], transport=None):
        self.settings = settings
        self.transport = transport
        self.observer = None

    async def extract(self, images: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": extraction_prompt(image.get("name", "") for image in images)}
        ]
        for image in images:
            content.append({"type": "image_url", "image_url": {"url": image["data_url"]}})
        result = await self._call("vision", content, ExtractedQuestions, coerce=self._unwrap_root)
        if not result.root:
            raise ProviderError("未识别到题目，请确认图片清晰且包含完整题目")
        return [item.model_dump() for item in result.root]

    @staticmethod
    def _unwrap_root(payload: Any) -> Any:
        # Some providers wrap the requested array in an object or return one bare item.
        if isinstance(payload, dict):
            if "kind" in payload or "text" in payload:
                return [payload]
            lists = [value for value in payload.values() if isinstance(value, list)]
            if len(lists) == 1:
                return lists[0]
        return payload

    async def extract_reference(self, images: List[Dict[str, str]]) -> Dict[str, Any]:
        content: List[Dict[str, Any]] = [{
            "type": "text",
            "text": reference_extraction_prompt(image.get("name", "") for image in images),
        }]
        content.extend(
            {"type": "image_url", "image_url": {"url": image["data_url"]}}
            for image in images
        )
        return (await self._call("vision", content, ReferenceExtraction)).model_dump()

    async def solve(self, question: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._call("solve", solve_prompt(question), Solution)
        if result.valid and result.status == "confirmed":
            self._validate_answer(question, result.answer)
        return result.model_dump()

    async def diagnose(
        self, question: Dict[str, Any], solution: Dict[str, Any], history: Any
    ) -> Dict[str, Any]:
        result = await self._call(
            "solve", diagnosis_prompt(question, solution, history), Diagnosis
        )
        return result.model_dump()

    async def chat(self, context: Any, text: str, mode: str) -> Dict[str, Any]:
        if mode not in {"direct", "hint"}:
            raise ProviderError("对话模式无效")
        return (await self._call("chat", chat_prompt(context, text, mode), ChatReply)).model_dump(
            exclude_none=True
        )

    async def generate(self, context: Any, purpose: str) -> Dict[str, Any]:
        if purpose not in {"variant", "verify", "prerequisite", "depth"}:
            raise ProviderError("训练目的无效")
        result = await self._call(
            "generate", generation_prompt(context, purpose), GeneratedQuestion
        )
        if result.purpose != purpose:
            raise ProviderError("模型响应格式不符合要求，请重试")
        return result.model_dump()

    async def verify(self, question: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._call("verify", verification_prompt(question), Verification)
        if result.valid:
            self._validate_answer(question, result.answer)
        return result.model_dump()

    @staticmethod
    def _validate_answer(question: Dict[str, Any], answer: Any) -> None:
        try:
            from .models import Option
            options = [Option.model_validate(item) for item in question.get("options", [])]
            validate_choice_answer(question.get("kind", "short"), options, answer)
        except (TypeError, ValueError, ValidationError):
            raise ProviderError("模型响应格式不符合要求，请重试") from None

    def _profile(self, task: str) -> Dict[str, Any]:
        profile_id = self.settings.get("tasks", {}).get(task)
        profile = next(
            (item for item in self.settings.get("profiles", []) if item.get("id") == profile_id),
            None,
        )
        if not profile:
            raise ProviderError(f"未配置 {task} 任务的模型")
        if not str(profile.get("api_key", "")).strip():
            raise ProviderError("未配置 API Key")
        for field in ("base_url", "model"):
            if not str(profile.get(field, "")).strip():
                raise ProviderError("模型配置不完整")
        return profile

    async def _call(
        self, task: str, content: Any, schema: Type[BaseModel], coerce=None
    ) -> BaseModel:
        profile = self._profile(task)
        started = time.monotonic()
        response = None
        success = False
        url = profile["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + profile["api_key"],
            "Content-Type": "application/json",
        }
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        limits = TASK_LIMITS.get(task, TASK_LIMITS["default"])
        body = {
            "model": profile["model"],
            "max_tokens": limits["max_tokens"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的电网学习助手。只返回符合以下完整 JSON Schema 的 JSON，"
                        "不得添加 Markdown 或 schema 之外字段：" + schema_json
                    ),
                },
                {"role": "user", "content": content},
            ],
        }
        # Opt-in GLM-style reasoning switch; providers without it stay untouched.
        if profile.get("disable_thinking"):
            body["thinking"] = {"type": "disabled"}
        try:
            timeout = httpx.Timeout(limits["timeout"])
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
                for attempt in range(2):
                    try:
                        response = await client.post(url, headers=headers, json=body)
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt == 0:
                            continue
                        raise ProviderError("模型服务暂时不可用，请稍后重试") from None
                    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
                        if attempt == 0:
                            continue
                        raise ProviderError("模型服务暂时不可用，请稍后重试")
                    if response.status_code >= 400:
                        raise ProviderError("模型服务拒绝了请求，请检查本地配置")
                    break
            envelope = response.json()
            raw = envelope["choices"][0]["message"]["content"]
            payload = self._parse_json(raw)
            if coerce is not None:
                payload = coerce(payload)
            result = schema.model_validate(payload)
            success = True
            return result
        except ProviderError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, ValidationError):
            raise ProviderError("模型响应格式不符合要求，请重试") from None
        finally:
            usage = {}
            if response is not None:
                try:
                    usage = response.json().get("usage") or {}
                except (ValueError, TypeError):
                    pass
            event = {
                "task": task,
                "profile_id": profile.get("id"),
                "model": profile.get("model"),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
                "success": success,
            }
            if self.observer:
                try:
                    observed = self.observer(event)
                    if inspect.isawaitable(observed):
                        await observed
                except Exception:
                    pass

    @staticmethod
    def _parse_json(raw: Any) -> Any:
        if not isinstance(raw, str):
            raise ValueError("content is not text")
        text = raw.strip()
        if text.startswith("```"):
            first_line, separator, remainder = text.partition("\n")
            if not separator or first_line not in {"```", "```json", "```JSON"}:
                raise ValueError("invalid JSON fence")
            body, separator, closing = remainder.rpartition("\n")
            if not separator or closing.strip() != "```":
                raise ValueError("invalid JSON fence")
            text = body.strip()
        return json.loads(text)
