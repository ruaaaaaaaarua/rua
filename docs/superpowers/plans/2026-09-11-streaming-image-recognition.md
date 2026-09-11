# 流式图片识别 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kimi 视觉识别通过 SSE 逐题推送到页面，且该路径强制禁用思考。

**Architecture:** Provider 将 Kimi SSE 转为模型内容文本；服务将换行 NDJSON 转为经 Pydantic 校验的题目并立即保存；FastAPI 将服务事件再次封装为本地 SSE；前端从 fetch ReadableStream 增量更新会话，done 后复用既有 GLM 自动分析。

**Tech Stack:** FastAPI、httpx、Pydantic、pytest、React、Vite、Vitest。

## Global Constraints

- 流式视觉请求必须设置 `stream: true` 和 `thinking: {"type":"disabled"}`。
- 只有完整并通过 `ExtractedQuestion` 校验的 NDJSON question 行能进入会话。
- 流式识别绝不创建 analysis、答案结论或 evidence。
- 所有 SSE 对外事件只能是 question、done 或安全 error；不暴露密钥、提示词或上游原始事件。
- `/extract` 与 `/analyze` 的非流式恢复兼容性不变。

---

### Task 1: Kimi SSE 内容流

**Files:**

- Modify: `tests/test_providers.py`
- Modify: `app/prompts.py`
- Modify: `app/providers.py`

**Interfaces:**

- Produces: `async ModelGateway.stream_extract(images) -> AsyncIterator[str]`，每个 yield 是 Kimi `delta.content` 的文本片段。

- [ ] **Step 1: 写失败 Provider 测试**

用 `httpx.MockTransport` 返回 `text/event-stream` 内容，调用 `stream_extract` 收集文本，并断言请求的 `stream` 为 true、`thinking.type` 为 disabled：

```python
@pytest.mark.anyio
async def test_stream_extract_disables_thinking_and_yields_delta_content():
    seen = {}
    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
            content=b'data: {"choices":[{"delta":{"content":"one"}}]}\n\n'
                    b'data: {"choices":[{"delta":{"content":" two"}}]}\n\n'
                    b'data: [DONE]\n\n')
    gateway = ModelGateway(settings(), httpx.MockTransport(handler))
    chunks = [part async for part in gateway.stream_extract([{'name':'q.png','data_url':'data:image/png;base64,AA=='}])]
    assert chunks == ['one', ' two']
    assert seen['stream'] is True
    assert seen['thinking'] == {'type':'disabled'}
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/bin/python -m pytest tests/test_providers.py::test_stream_extract_disables_thinking_and_yields_delta_content -q`

Expected: FAIL，因为 `stream_extract` 不存在。

- [ ] **Step 3: 实现最小流式 Provider**

新增 `stream_extraction_prompt(names)`，它要求无 Markdown 的 NDJSON question/done 行。新增 `stream_extract`：复用 profile、认证头和视觉 image_url；使用 `AsyncClient.stream('POST', ...)`，请求 body 含 stream 和强制禁用 thinking；遍历 `response.aiter_lines()`，只处理 `data: ` JSON 内的 `choices[0].delta.content`，忽略 `[DONE]` 与空 delta，HTTP/JSON 异常抛安全 `ProviderError`。

- [ ] **Step 4: 验证 Provider**

Run: `.venv/bin/python -m pytest tests/test_providers.py -q`

Expected: PASS。

### Task 2: 流式识别持久化与本地 SSE

**Files:**

- Modify: `tests/test_evidence_boundaries.py`
- Modify: `tests/test_api.py`
- Modify: `app/service.py`
- Modify: `app/main.py`

**Interfaces:**

- Produces: `async LearningService.extract_stream(session) -> AsyncIterator[dict]`，事件形状为 `{'type':'question','question':...}`、`{'type':'done'}` 或由路由构造的 error。
- Produces: `POST /api/sessions/{sid}/extract-stream`，content type 为 `text/event-stream`。

- [ ] **Step 1: 写服务失败测试**

使用会 yield 两个 NDJSON question 行和 done 行的 fake gateway。收集 `service.extract_stream` 事件，断言两个 question 在 done 前产生、session questions 为 2、每题无 analysis、knowledge 为空、会话最终 extracted。

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/bin/python -m pytest tests/test_evidence_boundaries.py::test_stream_extract_persists_each_valid_question_before_done -q`

Expected: FAIL，因为服务方法不存在。

- [ ] **Step 3: 实现服务转换**

调用 gateway `stream_extract`，按 `\n` 缓冲文本。每行 JSON 仅接受 `type == 'question'`；用 `ExtractedQuestion.model_validate(event['question'])` 校验，写入 question ID、附件 ID、revealed、知识归并、SQLite 后 yield。遇到 done 行后标附件 extracted、会话 extracted、yield done。未闭合或无有效题目抛 `ProviderError`。

- [ ] **Step 4: 写 API 失败测试**

对 TestClient 创建上传会话，调用 `/extract-stream`，断言响应 content-type 包含 text/event-stream，并从响应体依次读取 question 和 done。随后 GET session，断言题目已保存但没有 analysis。

- [ ] **Step 5: 实现 SSE 路由**

用异步生成器持有 `locked(sid)`；将 `extract_stream` 事件编码为 `event: <type>\ndata: <json>\n\n`，以 `StreamingResponse(..., media_type='text/event-stream')` 返回。捕获 `ProviderError` 后持久化 error 状态并发送安全 error 事件。

- [ ] **Step 6: 验证服务/API**

Run: `.venv/bin/python -m pytest tests/test_evidence_boundaries.py tests/test_api.py -q`

Expected: PASS。

### Task 3: 浏览器消费本地 SSE

**Files:**

- Modify: `web/src/api.js`
- Modify: `web/src/App.jsx`
- Modify: `web/src/domain.js`
- Modify: `web/src/domain.test.js`

**Interfaces:**

- Produces: `api.extractStream(id, {onQuestion}) -> Promise<session>`。
- Consumes: SSE question/done/error，done 后调用 `api.session(id)`。
- Produces: 上传流一到 question 就更新会话；done 后既有 extracted effect 触发 GLM。

- [ ] **Step 1: 写前端纯函数失败测试**

为 `parseSseFrames(buffer)` 写测试：两帧事件跨 buffer 输入时，返回完整 question，保留未完成尾部；done 事件独立返回。

- [ ] **Step 2: 运行并确认失败**

Run: `npm --prefix web test -- domain.test.js`

Expected: FAIL，因为解析器不存在。

- [ ] **Step 3: 实现并接入**

在 `domain.js` 实现 `parseSseFrames`。在 `api.js` 用 fetch 读取 reader、TextDecoder、解析帧；question 调 onQuestion，error throw，done 后请求 session。App 上传链改为 upload 后调用 extractStream；每个 question 用 `setSession` 追加，状态 recognizing；成功结果 `update` 后交给现有 extracted effect。

- [ ] **Step 4: 验证前端**

Run: `npm --prefix web test && npm --prefix web run build`

Expected: PASS。

### Task 4: 最终验证

- [ ] **Step 1: 运行全量自动化检查**

Run: `.venv/bin/python -m pytest -q && npm --prefix web test && npm --prefix web run build && git diff --check`

Expected: 全部成功。

- [ ] **Step 2: 真实 Kimi 性能试验**

上传同一张图，记录浏览器 Network 中 `/extract-stream` 的首个 question 事件时间与 done 时间。确认请求 body 包含 stream/禁用 thinking（只在本地调用记录中记录时长与 token，不记录密钥）。

- [ ] **Step 3: 不提交混合工作树**

`app/providers.py`、`app/service.py` 和测试文件含有本任务前未提交的批量分析修改；除已提交的设计文档外，不创建混合提交。

