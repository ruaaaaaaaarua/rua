import json

import httpx
import pytest

from app.providers import ModelGateway, ProviderError
from app.prompts import diagnosis_batch_prompt, solve_batch_prompt, stream_extraction_prompt
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


def test_stream_extraction_prompt_declares_complete_question_shape():
    prompt = stream_extraction_prompt(["page.png"])
    assert '"options":[{"key":"A","text":"选项内容"}]' in prompt
    assert 'subject、chapter、knowledge 均必须为非空的简短名称' in prompt
    assert '仅在题目或作答无法可靠转写时才写 recognition_note' in prompt


def test_batch_prompts_request_concise_output_without_unused_diagnosis_explanation():
    assert '一至两句' in solve_batch_prompt([])
    assert 'explanation' not in diagnosis_batch_prompt([])


def response(payload, status=200):
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


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
async def test_semantic_schema_rejections_record_failed_safe_telemetry():
    question = {
        "kind": "single", "text": "题",
        "options": [{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
    }
    cases = [
        (
            [],
            lambda gateway: gateway.extract([{"name": "blank.png", "data_url": "data:image/png;base64,AA=="}]),
            True,
        ),
        (
            [{"index": 0, "answer": "Z", "explanation": "越界", "valid": True, "status": "confirmed"}],
            lambda gateway: gateway.solve_batch([question]),
            False,
        ),
        (
            {"kind": "single", "text": "题", "options": [{"key": "A", "text": "甲"}], "answer": "A", "explanation": "理由", "knowledge_point": "知识", "knowledge": "知识", "purpose": "verify"},
            lambda gateway: gateway.generate({}, "variant"),
            True,
        ),
        (
            {"answer": "Z", "explanation": "理由", "valid": True},
            lambda gateway: gateway.verify(question),
            True,
        ),
    ]

    for payload, operation, raises_error in cases:
        observed = []
        gateway = ModelGateway(settings(), httpx.MockTransport(lambda request, payload=payload: response(payload)))
        gateway.observer = observed.append
        if raises_error:
            with pytest.raises(ProviderError, match="格式|未识别"):
                await operation(gateway)
        else:
            assert await operation(gateway) == []
        assert observed[-1]["success"] is False
        assert observed[-1]["error_kind"] == "response_schema"


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
async def test_verify_prompt_never_receives_generated_answer():
    captured = ""

    def handler(request):
        nonlocal captured
        captured = request.content.decode()
        return response(
            {"answer": "C", "explanation": "重新计算", "valid": True, "issues": []}
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    await gateway.verify(
        {
            "text": "验证题",
            "options": [{"key": "C", "text": "正确项"}],
            "answer": "TOP_SECRET_ANSWER",
            "explanation": "TOP_SECRET_EXPLANATION",
        }
    )
    assert "TOP_SECRET_ANSWER" not in captured
    assert "TOP_SECRET_EXPLANATION" not in captured


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
async def test_chat_can_return_a_strict_explicit_action_without_executing_it():
    def handler(request):
        return response(
            {
                "content": "好的，开始一道变式题。",
                "action": {
                    "type": "train",
                    "question_id": "q1",
                    "purpose": "variant",
                },
            }
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    result = await gateway.chat({"question_id": "q1"}, "给我一道变式题", "direct")
    assert result["action"] == {
        "type": "train",
        "question_id": "q1",
        "purpose": "variant",
    }


@pytest.mark.anyio
async def test_extract_accepts_fenced_json_and_preserves_learning_fields():
    payload = [
        {
            "number": 1,
            "kind": "single",
            "text": "电压题",
            "options": [{"key": "A", "text": "220V"}],
            "user_answer": "A",
            "reasoning": "铭牌可见",
            "confidence": "certain",
            "subject": "电工基础",
            "chapter": "电压",
            "knowledge": "额定电压",
            "recognition_note": None,
        }
    ]

    def handler(request):
        content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    result = await gateway.extract([{"name": "q.png", "data_url": "data:image/png;base64,AA=="}])
    assert result[0]["user_answer"] == "A"
    assert result[0]["reasoning"] == "铭牌可见"
    assert result[0]["subject"] == "电工基础"
    assert result[0]["knowledge"] == "额定电压"


@pytest.mark.anyio
async def test_diagnosis_supports_pending_and_nullable_correctness():
    def handler(request):
        return response(
            {
                "correct": None,
                "answer": "A",
                "knowledge_point": "保护配置",
                "diagnosis": "题干信息不足",
                "distinction": "需补充运行方式",
                "hint": "检查题干条件",
                "explanation": None,
                "reasoning_ok": None,
                "error_type": "insufficient_information",
                "status": "pending",
                "source": "model",
            }
        )

    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    result = await gateway.diagnose(
        {"text": "信息不完整", "user_answer": "A"},
        {"answer": "A", "explanation": "按现有条件"},
        [],
    )
    assert result["correct"] is None
    assert result["reasoning_ok"] is None
    assert result["status"] == "pending"


@pytest.mark.anyio
async def test_extract_normalizes_answers_and_rejects_empty_result():
    payload = [{
        "number": "12a", "kind": "multiple", "text": "多选题",
        "options": [{"key": "A", "text": "甲"}, {"key": "C", "text": "丙"}],
        "user_answer": ["C", "A"], "reasoning": None, "confidence": "certain",
        "subject": "继保", "chapter": "配置", "knowledge": "保护配置",
    }]
    gateway = ModelGateway(settings(), httpx.MockTransport(lambda request: response(payload)))
    result = await gateway.extract([{"name": "q.png", "data_url": "data:image/png;base64,AA=="}])
    assert result[0]["number"] == "12a"
    assert result[0]["user_answer"] == "AC"
    assert result[0]["reasoning"] == ""

    empty = ModelGateway(settings(), httpx.MockTransport(lambda request: response([])))
    with pytest.raises(ProviderError, match="未识别到题目"):
        await empty.extract([{"name": "blank.png", "data_url": "data:image/png;base64,AA=="}])


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
async def test_generate_validates_choice_structure_and_short_answer():
    invalid = {
        "kind": "multiple", "text": "题", "options": [{"key": "A", "text": "甲"}],
        "answer": ["A", "A"], "explanation": "理由", "knowledge_point": "知识",
        "knowledge": "目标知识", "subject": "继保", "chapter": "配置", "purpose": "variant",
    }
    gateway = ModelGateway(settings(), httpx.MockTransport(lambda request: response(invalid)))
    with pytest.raises(ProviderError, match="响应格式"):
        await gateway.generate({}, "variant")


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
async def test_prompts_exclude_learning_leakage_and_diagnosis_allows_empty_distinction():
    seen = []
    replies = [
        {"answer": "A", "explanation": "理由"},
        {"answer": "A", "explanation": "理由", "valid": True, "issues": []},
        {"correct": True, "answer": "A", "knowledge_point": "知识", "diagnosis": "答对",
         "distinction": "", "hint": "继续", "explanation": None, "reasoning_ok": None,
         "error_type": "unknown", "status": "confirmed", "source": "model"},
    ]
    def handler(request):
        seen.append(request.content.decode())
        return response(replies.pop(0))
    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    leaked = {"kind": "single", "text": "题", "options": [{"key": "A", "text": "甲"}],
              "knowledge_point": "LEAK_KP", "lesson": "LEAK_LESSON", "answer": "LEAK_ANSWER",
              "explanation": "LEAK_EXPLANATION"}
    await gateway.solve(leaked)
    await gateway.verify(leaked)
    diagnosis = await gateway.diagnose({**leaked, "user_answer": "A"}, {"answer": "A"}, [])
    assert diagnosis["correct"] is True and diagnosis["status"] == "confirmed"
    assert all(secret not in seen[0] and secret not in seen[1] for secret in
               ("LEAK_KP", "LEAK_LESSON", "LEAK_ANSWER", "LEAK_EXPLANATION"))


@pytest.mark.anyio
async def test_answers_are_normalized_and_observer_gets_safe_usage():
    observed = []
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({
                "content": "收到", "action": {
                    "type": "answer_quiz", "quiz_id": "quiz-1", "answer": ["C", "A"]
                }
            })}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 9},
        })
    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    gateway.observer = observed.append
    result = await gateway.chat({}, "我选 AC", "direct")
    assert result["action"]["answer"] == "AC"
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
async def test_diagnose_batch_maps_results_by_index():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return response(
            [
                {
                    "index": 1,
                    "correct": True,
                    "knowledge_point": "平方关系",
                    "diagnosis": "",
                    "distinction": "",
                    "hint": "检查指数",
                    "reasoning_ok": None,
                    "status": "confirmed",
                }
            ]
        )

    config = settings(); config["profiles"][1]["model"] = "glm-5.3-flash"
    gateway = ModelGateway(config, httpx.MockTransport(handler))
    items = await gateway.diagnose_batch(
        [
            {"index": 0, "question": {"kind": "single"}, "independent_solution": {"answer": "B"}},
            {"index": 1, "question": {"kind": "single"}, "independent_solution": {"answer": "B"}},
        ]
    )
    assert [item["index"] for item in items] == [1]
    assert "thinking" not in captured
    assert captured["reasoning_effort"] == "low"
    assert captured["max_tokens"] == 4096


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
