import json

import httpx
import pytest

from app.providers import ModelGateway, ProviderError
from app.prompts import solve_batch_prompt, stream_extraction_prompt
from app.store import Store


@pytest.fixture
def anyio_backend():
    return "asyncio"


def settings(api_key="secret-key"):
    return {
        "profiles": [
            {
                "id": "vision-profile",
                "name": "Vision",
                "base_url": "https://vision.example/v1",
                "model": "vision-model",
                "api_key": api_key,
            },
            {
                "id": "text-profile",
                "name": "Text",
                "base_url": "https://text.example/v1/",
                "model": "text-model",
                "api_key": api_key,
            },
        ],
        "tasks": {
            "vision": "vision-profile",
            "solve": "text-profile",
            "chat": "text-profile",
            "generate": "text-profile",
            "verify": "text-profile",
        },
    }


def response(payload, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


def test_profile_parallel_takes_precedence_over_legacy_global_parallel():
    config = settings()
    config["parallel"] = 2
    config["profiles"][1]["parallel"] = 3

    gateway = ModelGateway(config)

    assert gateway.parallel_for("solve") == 3


def test_distinct_profile_account_identities_have_distinct_rate_keys():
    config_a = settings(api_key="account-a")
    config_b = settings(api_key="account-b")
    gateway_a = ModelGateway(config_a)
    gateway_b = ModelGateway(config_b)
    profile_a = config_a["profiles"][1]
    profile_b = config_b["profiles"][1]

    assert gateway_a.rate_key(profile_a) != gateway_b.rate_key(profile_b)


@pytest.mark.anyio
async def test_response_schema_failure_records_safe_error_kind(tmp_path):
    store = Store(tmp_path)
    gateway = ModelGateway(settings(), httpx.MockTransport(lambda request: response({"answer": "A"})))
    gateway.observer = store.record_call

    with pytest.raises(ProviderError, match="响应格式"):
        await gateway.solve({"text": "题目", "user_answer": "B"})

    with store.connect() as db:
        event = json.loads(db.execute("SELECT data FROM calls").fetchone()["data"])
    assert event["error_kind"] == "response_schema"


@pytest.mark.anyio
async def test_out_of_range_batch_index_is_rejected_before_success_telemetry():
    observed = []
    gateway = ModelGateway(
        settings(),
        httpx.MockTransport(lambda request: response([
            {"index": 1, "answer": "A", "explanation": "越界", "valid": True, "status": "confirmed"},
        ])),
    )
    gateway.observer = observed.append

    items = await gateway.solve_batch([{
        "kind": "single", "text": "题", "options": [{"key": "A", "text": "甲"}],
    }])

    assert items == []
    assert observed[-1]["success"] is False
    assert observed[-1]["error_kind"] == "response_schema"


@pytest.mark.anyio
async def test_missing_api_key_fails_without_network_call():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return response({"answer": "A", "explanation": "原因"})

    gateway = ModelGateway(settings(api_key=""), httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="未配置 API Key"):
        await gateway.solve({"text": "题目", "user_answer": "B"})
    assert calls == 0


@pytest.mark.anyio
async def test_task_routing_and_solve_prompt_redacts_student_work():
    seen = []

    def handler(request):
        seen.append((request.url, json.loads(request.content)))
        return response({"answer": "A", "explanation": "独立求解"})

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    result = await gateway.solve(
        {
            "text": "哪项正确？",
            "options": [{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
            "user_answer": "B",
            "reasoning": "我猜 B",
            "confidence": "guess",
            "analysis": {"answer": "B"},
            "answer": "B",
        }
    )

    assert result == {
        "answer": "A",
        "explanation": "独立求解",
        "valid": True,
        "status": "confirmed",
    }
    url, body = seen[0]
    assert str(url) == "https://text.example/v1/chat/completions"
    assert body["model"] == "text-model"
    prompt = json.dumps(body["messages"], ensure_ascii=False)
    for secret in ("我猜 B", '"user_answer"', '"confidence"', '"analysis"'):
        assert secret not in prompt


@pytest.mark.anyio
async def test_invalid_json_schema_raises_safe_provider_error():
    def handler(request):
        return response({"unexpected": True})

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await gateway.solve({"text": "题目"})
    assert "secret-key" not in str(caught.value)
    assert "响应格式" in str(caught.value)


@pytest.mark.anyio
async def test_transient_failure_is_retried_at_most_twice():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="upstream leaked secret-key")

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await gateway.chat({}, "你好", "direct")
    assert calls == 2
    assert "secret-key" not in str(caught.value)
    assert "upstream leaked" not in str(caught.value)


@pytest.mark.anyio
async def test_system_message_contains_full_json_schema():
    captured = {}
    def handler(request):
        captured.update(json.loads(request.content))
        return response({"answer": "A", "explanation": "理由"})
    await ModelGateway(settings(), httpx.MockTransport(handler)).solve({
        "kind": "single", "text": "题目", "options": [{"key": "A", "text": "甲"}]
    })
    system = captured["messages"][0]["content"]
    assert '"enum":["confirmed","pending"]' in system
    assert '"additionalProperties":false' in system
    assert '"title":"Solution"' in system


@pytest.mark.anyio
async def test_solve_choice_answer_must_match_question_structure():
    gateway = ModelGateway(settings(), httpx.MockTransport(
        lambda request: response({"answer": "C", "explanation": "理由"})
    ))
    with pytest.raises(ProviderError, match="响应格式"):
        await gateway.solve({"kind": "single", "text": "题", "options": [
            {"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}
        ]})


@pytest.mark.anyio
async def test_extract_reference_uses_vision_and_returns_content():
    captured = {}
    def handler(request):
        captured.update(json.loads(request.content))
        return response({"content": "图中参考答案为 A，依据是额定电压。"})
    result = await ModelGateway(settings(), httpx.MockTransport(handler)).extract_reference([
        {"name": "reference.png", "data_url": "data:image/png;base64,AA=="}
    ])
    assert result == {"content": "图中参考答案为 A，依据是额定电压。"}
    assert captured["model"] == "vision-model"


@pytest.mark.anyio
async def test_chat_observer_gets_safe_usage():
    observed = []
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({
                "content": "收到"
            })}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 9},
        })
    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    gateway.observer = observed.append
    result = await gateway.chat({}, "我选 AC", "direct")
    assert result["content"] == "收到"
    assert observed == [{
        "task": "chat", "profile_id": "text-profile", "model": "text-model",
        "input_tokens": 123, "output_tokens": 9,
        "duration_ms": observed[0]["duration_ms"], "success": True,
    }]
    assert observed[0]["duration_ms"] >= 0
    assert "api_key" not in observed[0] and "prompt" not in observed[0]


@pytest.mark.anyio
async def test_solve_batch_prompt_redacts_student_work():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return response([{"index": 0, "answer": "B", "explanation": "平方", "valid": True, "status": "confirmed"}])

    config = settings(); config["profiles"][1]["model"] = "glm-5.3-flash"
    gateway = ModelGateway(config, httpx.MockTransport(handler))
    items = await gateway.solve_batch(
        [
            {
                "text": "电压翻倍，功率？",
                "kind": "single",
                "options": [{"key": "A", "text": "2倍"}, {"key": "B", "text": "4倍"}],
                "user_answer": "A",
                "reasoning": "我猜一次关系",
                "confidence": "guess",
            }
        ]
    )
    assert items == [{"index": 0, "answer": "B", "explanation": "平方", "valid": True, "status": "confirmed"}]
    assert "thinking" not in captured["body"]
    assert captured["body"]["reasoning_effort"] == "low"
    assert captured["body"]["max_tokens"] == 4096
    content = captured["body"]["messages"][1]["content"]
    assert "user_answer" not in content and "我猜一次关系" not in content and "guess" not in content


@pytest.mark.anyio
async def test_solve_batch_drops_items_with_invalid_answers():
    def handler(request):
        return response(
            [
                {"index": 0, "answer": "B", "explanation": "平方", "valid": True, "status": "confirmed"},
                {"index": 1, "answer": "Z", "explanation": "越界选项", "valid": True, "status": "confirmed"},
            ]
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    question = {
        "text": "题",
        "kind": "single",
        "options": [{"key": "A", "text": "1"}, {"key": "B", "text": "2"}],
    }
    items = await gateway.solve_batch([question, dict(question)])
    assert [item["index"] for item in items] == [0]


@pytest.mark.anyio
async def test_stream_extract_disables_thinking_and_yields_delta_content():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"content":"one"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":" two"}}]}\n\n'
                b'data: [DONE]\n\n'
            ),
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    chunks = [
        part
        async for part in gateway.stream_extract(
            [{"name": "q.png", "data_url": "data:image/png;base64,AA=="}]
        )
    ]

    assert chunks == ["one", " two"]
    assert seen["stream"] is True
    assert seen["thinking"] == {"type": "disabled"}
    assert seen["max_tokens"] == 8192
