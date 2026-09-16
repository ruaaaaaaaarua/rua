import asyncio
import hashlib
import json
import inspect
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, ValidationError

from .models import (
    BatchedSolutions,
    ChatReply,
    ExtractedQuestions,
    ReferenceExtraction,
    Solution,
    validate_choice_answer,
)
from .prompts import (
    chat_prompt,
    extraction_prompt,
    reference_extraction_prompt,
    solve_batch_prompt,
    solve_prompt,
    stream_chat_prompt,
    stream_extraction_prompt,
)


SAFE_ERROR_KINDS = frozenset({
    "provider_error",
    "configuration",
    "provider_rate_limited",
    "provider_rejected",
    "provider_unavailable",
    "request_invalid",
    "response_schema",
})


def normalize_error_kind(error_kind: Any) -> str:
    return error_kind if error_kind in SAFE_ERROR_KINDS else "provider_error"


class ProviderError(RuntimeError):
    """A provider failure safe to display to a local user."""

    def __init__(self, message: str, error_kind: str = "provider_error"):
        super().__init__(message)
        self.error_kind = normalize_error_kind(error_kind)


# Whole-page transcription needs thousands of tokens; provider defaults cap far too low.
TASK_LIMITS = {
    # Vision thinking length varies wildly run to run; a tight cap truncates
    # the transcription JSON mid-array (observed at 16k on a dense page).
    "vision": {"max_tokens": 32768, "timeout": 420.0},
    "solve": {"max_tokens": 4096, "timeout": 180.0},
    "chat": {"max_tokens": 4096, "timeout": 180.0},
    "default": {"max_tokens": 16384, "timeout": 180.0},
}


class ModelGateway:
    # Fresh provider accounts cap tokens per minute; a whole-page vision
    # transcription drains that window and starves the solving phase.
    RATE_WINDOW = 60.0
    DEFAULT_RATE_BUDGET = 15000
    # Shared per process, but only between gateways using the same account.
    _usage_events: Dict[str, list] = {}

    def __init__(self, settings: Dict[str, Any], transport=None):
        self.settings = settings
        self.transport = transport
        self.observer = None
        self.rate_budget = int(settings.get("rate_tpm") or self.DEFAULT_RATE_BUDGET)

    @staticmethod
    def rate_key(profile: Dict[str, Any]) -> str:
        identity = "\0".join((profile["base_url"], profile["model"], profile["api_key"]))
        return hashlib.sha256(identity.encode()).hexdigest()

    def parallel_for(self, task: str) -> int:
        profile = self._profile(task)
        return int(profile.get("parallel") or self.settings.get("parallel") or (2 if task == 'solve' else 1))

    async def _await_token_budget(self, profile: Dict[str, Any]) -> None:
        events = self._usage_events.setdefault(self.rate_key(profile), [])
        while events:
            now = time.monotonic()
            events[:] = [
                (at, tokens)
                for at, tokens in events
                if now - at < self.RATE_WINDOW
            ]
            if sum(tokens for _, tokens in events) < self.rate_budget:
                return
            oldest = events[0][0]
            await asyncio.sleep(min(62.0, max(2.0, self.RATE_WINDOW - (now - oldest) + 2.0)))

    def _note_usage(self, profile: Dict[str, Any], usage: Dict[str, Any]) -> None:
        tokens = usage.get("completion_tokens") or 0
        if tokens:
            self._usage_events.setdefault(self.rate_key(profile), []).append((time.monotonic(), tokens))

    async def extract(self, images: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": extraction_prompt(image.get("name", "") for image in images)}
        ]
        for image in images:
            content.append({"type": "image_url", "image_url": {"url": image["data_url"]}})
        result = await self._call(
            "vision", content, ExtractedQuestions, coerce=self._unwrap_root,
            semantic_error_kind=lambda parsed: "response_schema" if not parsed.root else None,
        )
        if not result.root:
            raise ProviderError("未识别到题目，请确认图片清晰且包含完整题目", "response_schema")
        return [item.model_dump() for item in result.root]

    async def stream_extract(self, images: List[Dict[str, str]]) -> AsyncIterator[str]:
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": stream_extraction_prompt(image.get("name", "") for image in images)}
        ]
        content.extend(
            {"type": "image_url", "image_url": {"url": image["data_url"]}}
            for image in images
        )
        async for part in self._stream("vision", content, max_tokens=8192):
            yield part

    @staticmethod
    def _retry_delay(response, floor: float = 5.0, ceiling: float = 30.0) -> float:
        header = response.headers.get("retry-after", "")
        try:
            return max(floor, min(ceiling, float(header)))
        except ValueError:
            return min(ceiling, max(floor, 12.0))

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
        result = await self._call(
            "solve", solve_prompt(question), Solution,
            semantic_error_kind=lambda parsed: self._answer_error_kind(question, parsed),
        )
        if result.valid and result.status == "confirmed":
            self._validate_answer(question, result.answer)
        return result.model_dump()

    async def solve_batch(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = await self._call(
            "solve", solve_batch_prompt(questions), BatchedSolutions, coerce=self._unwrap_root, batch=True,
            semantic_error_kind=lambda parsed: self._batch_answer_error_kind(parsed, questions),
        )
        items: List[Dict[str, Any]] = []
        for item in result.root:
            if item.index >= len(questions):
                continue
            if item.valid and item.status == "confirmed" and item.index < len(questions):
                try:
                    self._validate_answer(questions[item.index], item.answer)
                except ProviderError:
                    continue
            items.append(item.model_dump())
        return items

    async def chat(self, context: Any, text: str, mode: str) -> Dict[str, Any]:
        if mode not in {"direct", "hint"}:
            raise ProviderError("对话模式无效", "request_invalid")
        return (await self._call("chat", chat_prompt(context, text, mode), ChatReply)).model_dump(
            exclude_none=True
        )

    async def stream_chat(
        self, context: Any, text: str, mode: str = "direct"
    ) -> AsyncIterator[str]:
        if mode not in {"direct", "hint"}:
            raise ProviderError("对话模式无效", "request_invalid")
        async for part in self._stream(
            "chat",
            stream_chat_prompt(context, text, mode),
            system_instruction="你是严谨的电网学习助手。请直接回复纯文本或 Markdown。",
        ):
            yield part

    @staticmethod
    def _validate_answer(question: Dict[str, Any], answer: Any) -> None:
        try:
            from .models import Option
            options = [Option.model_validate(item) for item in question.get("options", [])]
            validate_choice_answer(question.get("kind", "single"), options, answer)
        except (TypeError, ValueError, ValidationError):
            raise ProviderError("模型响应格式不符合要求，请重试", "response_schema") from None

    def _answer_error_kind(self, question: Dict[str, Any], result: BaseModel) -> Optional[str]:
        if not getattr(result, "valid", False) or getattr(result, "status", "confirmed") != "confirmed":
            return None
        try:
            self._validate_answer(question, result.answer)
        except ProviderError as exc:
            return exc.error_kind
        return None

    def _batch_answer_error_kind(
        self, result: BaseModel, questions: List[Dict[str, Any]]
    ) -> Optional[str]:
        for item in result.root:
            if item.index >= len(questions):
                return "response_schema"
            if item.valid and item.status == "confirmed" and item.index < len(questions):
                error_kind = self._answer_error_kind(questions[item.index], item)
                if error_kind:
                    return error_kind
        return None

    def _profile(self, task: str) -> Dict[str, Any]:
        profile_id = self.settings.get("tasks", {}).get(task)
        profile = next(
            (item for item in self.settings.get("profiles", []) if item.get("id") == profile_id),
            None,
        )
        if not profile:
            raise ProviderError(f"未配置 {task} 任务的模型", "configuration")
        if not str(profile.get("api_key", "")).strip():
            raise ProviderError("未配置 API Key", "configuration")
        for field in ("base_url", "model"):
            if not str(profile.get(field, "")).strip():
                raise ProviderError("模型配置不完整", "configuration")
        return profile

    async def _stream(
        self, task: str, content: Any, max_tokens: Optional[int] = None,
        system_instruction: Optional[str] = None,
    ) -> AsyncIterator[str]:
        profile = self._profile(task)
        await self._await_token_budget(profile)
        started = time.monotonic()
        success = False
        error_kind = None
        usage: Dict[str, Any] = {}
        limits = TASK_LIMITS.get(task, TASK_LIMITS["default"])
        body = {
            "model": profile["model"],
            "max_tokens": max_tokens or limits["max_tokens"],
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [
                {"role": "system", "content": system_instruction or "你是严谨的电网学习助手。按用户指定的 NDJSON 协议输出。"},
                {"role": "user", "content": content},
            ],
        }
        if task == "vision":
            body["thinking"] = {"type": "disabled"}
        elif profile["model"].casefold().startswith("glm-5.3"):
            body["reasoning_effort"] = "low"
        elif profile.get("disable_thinking"):
            body["thinking"] = {"type": "disabled"}
        headers = {"Authorization": "Bearer " + profile["api_key"], "Content-Type": "application/json"}
        url = profile["base_url"].rstrip("/") + "/chat/completions"
        try:
            timeout = httpx.Timeout(limits["timeout"])
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code >= 400:
                        if response.status_code == 429:
                            raise ProviderError("模型服务限流，请稍后重试", "provider_rate_limited")
                        if response.status_code >= 500:
                            raise ProviderError("模型服务暂时不可用，请稍后重试", "provider_unavailable")
                        raise ProviderError("模型服务拒绝了请求，请检查本地配置", "provider_rejected")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            success = True
                            return
                        try:
                            frame = json.loads(data)
                            if not isinstance(frame, dict):
                                raise TypeError("SSE frame is not an object")
                            frame_usage = frame.get("usage")
                            if frame_usage is not None and not isinstance(frame_usage, dict):
                                raise TypeError("SSE usage is not an object")
                            if frame_usage:
                                usage = frame_usage
                            choices = frame.get("choices") or []
                            delta = choices[0].get("delta", {}).get("content") if choices else None
                            finish = choices[0].get("finish_reason") if choices else None
                        except (AttributeError, TypeError, ValueError, KeyError, IndexError):
                            raise ProviderError("模型流式响应格式不符合要求，请重试", "response_schema") from None
                        if finish in {"length", "content_filter"}:
                            raise ProviderError("模型输出被截断或拦截，请重试", "response_schema")
                        if delta and not isinstance(delta, str):
                            raise ProviderError("模型流式响应格式不符合要求，请重试", "response_schema")
                        if delta:
                            yield delta
            raise ProviderError("模型流式响应提前结束，请重试", "response_schema")
        except ProviderError as exc:
            error_kind = exc.error_kind
            raise
        except (httpx.TimeoutException, httpx.NetworkError):
            error_kind = "provider_unavailable"
            raise ProviderError("模型服务暂时不可用，请稍后重试", error_kind) from None
        finally:
            self._note_usage(profile, usage)
            event = {
                "task": task,
                "profile_id": profile.get("id"),
                "model": profile.get("model"),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
                "success": success,
            }
            if error_kind:
                event["error_kind"] = error_kind
            if self.observer:
                try:
                    observed = self.observer(event)
                    if inspect.isawaitable(observed):
                        await observed
                except Exception:
                    pass

    async def _call(
        self, task: str, content: Any, schema: Type[BaseModel], coerce=None, batch: bool = False,
        semantic_error_kind: Optional[Callable[[BaseModel], Optional[str]]] = None,
    ) -> BaseModel:
        profile = self._profile(task)
        await self._await_token_budget(profile)
        started = time.monotonic()
        response = None
        success = False
        error_kind = None
        url = profile["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + profile["api_key"],
            "Content-Type": "application/json",
        }
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        limits = TASK_LIMITS.get(task, TASK_LIMITS["default"])
        body = {
            "model": profile["model"],
            "max_tokens": 4096 if batch else limits["max_tokens"],
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
        # GLM 5.3 uses low reasoning for both ordinary and batched text work.
        if profile["model"].casefold().startswith("glm-5.3"):
            body["reasoning_effort"] = "low"
        elif batch or profile.get("disable_thinking"):
            body["thinking"] = {"type": "disabled"}
        try:
            timeout = httpx.Timeout(limits["timeout"])
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
                response = None
                attempt = 0
                while True:
                    try:
                        response = await client.post(url, headers=headers, json=body)
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt < 1:
                            await asyncio.sleep(5)
                            attempt += 1
                            continue
                        raise ProviderError("模型服务暂时不可用，请稍后重试", "provider_unavailable") from None
                    if response.status_code == 429:
                        # Token-window limits need a real pause, not a quick retry.
                        if attempt < 2:
                            await asyncio.sleep(self._retry_delay(response, 20.0, 60.0))
                            attempt += 1
                            continue
                        raise ProviderError("模型服务限流，请稍后重试", "provider_rate_limited")
                    if response.status_code in {408, 409, 425} or response.status_code >= 500:
                        if attempt < 1:
                            await asyncio.sleep(5)
                            attempt += 1
                            continue
                        raise ProviderError("模型服务暂时不可用，请稍后重试", "provider_unavailable")
                    if response.status_code >= 400:
                        raise ProviderError("模型服务拒绝了请求，请检查本地配置", "provider_rejected")
                    break
            envelope = response.json()
            raw = envelope["choices"][0]["message"]["content"]
            payload = self._parse_json(raw)
            if coerce is not None:
                payload = coerce(payload)
            result = schema.model_validate(payload)
            if semantic_error_kind:
                semantic_kind = semantic_error_kind(result)
                if semantic_kind:
                    error_kind = normalize_error_kind(semantic_kind)
            success = error_kind is None
            return result
        except ProviderError as exc:
            error_kind = exc.error_kind
            raise
        except (ValueError, TypeError, KeyError, IndexError, ValidationError):
            error_kind = "response_schema"
            raise ProviderError("模型响应格式不符合要求，请重试", error_kind) from None
        finally:
            usage = {}
            if response is not None:
                try:
                    usage = response.json().get("usage") or {}
                except (ValueError, TypeError):
                    pass
            # Truncated generations still drain the provider window; count any
            # usage the service reported, success or not.
            self._note_usage(profile, usage)
            event = {
                "task": task,
                "profile_id": profile.get("id"),
                "model": profile.get("model"),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
                "success": success,
            }
            if error_kind:
                event["error_kind"] = error_kind
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
