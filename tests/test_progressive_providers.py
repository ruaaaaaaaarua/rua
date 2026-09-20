import json

import httpx
import pytest

from app.providers import ModelGateway, ProviderError
from app.prompts import solve_batch_prompt, extraction_prompt


@pytest.fixture
def anyio_backend():
    return "asyncio"


def settings(model="glm-5.3-flash"):
    return {
        "profiles": [
            {
                "id": "vision",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-flash",
                "api_key": "test-vision-key",
            },
            {
                "id": "text",
                "base_url": "https://text.example/v1",
                "model": model,
                "api_key": "test-text-key",
                "disable_thinking": True,
            },
        ],
        "tasks": {"vision": "vision", "solve": "text", "chat": "text"},
    }


def sse(*frames):
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join(f"data: {frame}\n\n" for frame in frames).encode(),
    )


@pytest.mark.anyio
async def test_stream_chat_uses_plain_text_policy_and_glm_low_reasoning():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return sse(
            json.dumps({"choices": [{"delta": {"content": "简洁"}}]}),
            json.dumps({"choices": [{"delta": {"content": "讲解"}}]}),
            "[DONE]",
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    chunks = [part async for part in gateway.stream_chat({"question": "Q"}, "为什么？")]

    assert chunks == ["简洁", "讲解"]
    assert captured["reasoning_effort"] == "low"
    assert "thinking" not in captured
    assert captured["stream_options"] == {"include_usage": True}
    assert "JSON" not in captured["messages"][0]["content"]
    assert "默认简洁" in captured["messages"][1]["content"]


@pytest.mark.anyio
async def test_stream_chat_accepts_usage_only_frame_and_records_usage():
    observed = []

    def handler(request):
        return sse(
            json.dumps({"choices": [{"delta": {"content": "收到"}}]}),
            json.dumps({"choices": [], "usage": {"prompt_tokens": 17, "completion_tokens": 3}}),
            "[DONE]",
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    gateway.observer = observed.append
    assert [part async for part in gateway.stream_chat({}, "你好")] == ["收到"]
    assert observed[-1]["input_tokens"] == 17
    assert observed[-1]["output_tokens"] == 3
    assert observed[-1]["success"] is True


@pytest.mark.anyio
async def test_stream_chat_rejects_truncated_stream_with_safe_error():
    gateway = ModelGateway(
        settings(),
        httpx.MockTransport(lambda request: sse(
            json.dumps({"choices": [{"delta": {"content": "只有一半"}}]}),
        )),
    )

    with pytest.raises(ProviderError) as caught:
        _ = [part async for part in gateway.stream_chat({}, "解释")]
    assert caught.value.error_kind == "response_schema"
    assert "test-text-key" not in str(caught.value)


@pytest.mark.anyio
async def test_stream_chat_wraps_wrong_sse_shape_as_safe_schema_error():
    gateway = ModelGateway(
        settings(), httpx.MockTransport(lambda request: sse('["not-an-object"]', "[DONE]"))
    )

    with pytest.raises(ProviderError) as caught:
        _ = [part async for part in gateway.stream_chat({}, "解释")]
    assert caught.value.error_kind == "response_schema"
    assert "流式响应格式" in str(caught.value)


@pytest.mark.anyio
async def test_vision_stream_disables_thinking_but_never_uses_glm_reasoning():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return sse("[DONE]")

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    assert [part async for part in gateway.stream_extract([])] == []
    assert captured["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in captured


@pytest.mark.anyio
async def test_ordinary_glm_solve_and_chat_use_low_reasoning_with_bounded_budgets():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            payload = {"answer": "A", "explanation": "依据"}
        else:
            payload = {"content": "回复"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    await gateway.solve({"kind": "single", "text": "Q", "options": [{"key": "A", "text": "a"}]})
    await gateway.chat({}, "你好", "direct")

    assert [body["reasoning_effort"] for body in bodies] == ["low", "low"]
    assert all("thinking" not in body for body in bodies)
    assert 1024 <= bodies[0]["max_tokens"] <= 4096
    assert 1024 <= bodies[1]["max_tokens"] <= 4096


def test_batch_prompt_keeps_questions_independent_and_excludes_student_work():
    prompt = solve_batch_prompt([
        {"text": "Q1", "kind": "single", "options": [], "user_answer": "SECRET-A"},
        {"text": "Q2", "kind": "judge", "options": [], "reasoning": "SECRET-B"},
    ])

    assert "题目间互不影响" in prompt
    assert "Q1" in prompt and "Q2" in prompt
    assert "SECRET-A" not in prompt and "SECRET-B" not in prompt


@pytest.mark.anyio
async def test_stream_token_limit_is_not_reported_as_completed_reply():
    gateway = ModelGateway(settings(), httpx.MockTransport(lambda request: sse(
        json.dumps({'choices': [{'delta': {'content': '未完成'}, 'finish_reason': None}]}),
        json.dumps({'choices': [{'delta': {}, 'finish_reason': 'length'}]}),
        '[DONE]',
    )))
    with pytest.raises(ProviderError, match='截断'):
        _ = [part async for part in gateway.stream_chat({}, '讲解')]


def test_vision_prompt_preserves_section_kind_and_reports_incomplete_questions():
    prompt = extraction_prompt(['page.jpg'])
    assert '分区标题' in prompt and 'incomplete' in prompt
    assert '不能凭已选答案数量' in prompt
