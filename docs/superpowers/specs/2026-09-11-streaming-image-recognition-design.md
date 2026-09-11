# 流式图片识别首屏设计

**状态：** 已确认  
**日期：** 2026-09-11

## 目标

让用户上传一张题图后，在 Kimi 视觉模型开始输出时逐题显示识别结果，而不是等待整页严格 JSON 完成。该首屏路径强制关闭 Kimi 思考；完整的 GLM 独立解题、诊断、答案泄露保护和学习证据规则保持不变。

## 选择的方案

新增端到端 SSE 提取接口：

```text
浏览器 POST /extract-stream
  → 后端请求 Kimi（stream: true，thinking: disabled）
  → Kimi 增量输出一题一行 NDJSON
  → 后端校验每题并保存到 SQLite
  → SSE question 事件推给浏览器，立即显示
  → SSE done 事件
  → 浏览器获取会话并自动 POST /analyze
  → GLM 批量解题与诊断
```

Kimi 请求不再要求一个整页 JSON 数组，而要求每行一个 `{"type":"question","question":{...}}` 事件，并以 `{"type":"done"}` 结束。服务层只接受通过 `ExtractedQuestion` Pydantic 校验的完整行；增量字符和半行不保存、不展示为有效题目。

## 后端边界

`ModelGateway.stream_extract(images)` 是异步迭代器。它构造视觉请求，始终传递 `stream: true` 和 `thinking: {"type":"disabled"}`，逐个解析 Kimi SSE `data:` 负载中的 `choices[0].delta.content` 文本片段。网络、HTTP、SSE 外层 JSON 或模型内容异常转换为已有的 `ProviderError`。

`LearningService.extract_stream(session)` 缓冲模型文本到换行边界，解析 NDJSON。每个有效 question 立刻补充本地 ID、附件 ID、`revealed: false`，执行知识名归并并持久化，然后产生 `question` 事件。完成时将附件标记为 extracted、会话标为 extracted 并产生 `done`。该阶段不写 analysis 或 evidence。

`POST /api/sessions/{sid}/extract-stream` 用 `StreamingResponse` 包住服务异步迭代器，并在整个流期间保持该会话锁。SSE 事件只传 question、done 或安全错误消息，不传密钥、提示词、模型原始 SSE 或答案。若模型不支持流式提取、流中断或产生无效内容，端点发出 error；已有逐题识别结果保留，但不会创建学习证据。现有 `/extract` 与 `/analyze` 保持为非流式恢复路径。

## 前端行为

上传后页面立即进入 recognizing 状态并建立 SSE。每收到一个 question 事件，将它追加进当前会话并展示为“已识别，待分析”。收到 done 后重新读取会话；现有 extracted 自动续跑机制调用 GLM 分析。收到 error 时停止加载，显示安全错误和“重试识别”入口；用户仍可核对已成功保存的题目。

浏览器解析以 SSE 空行分帧，支持多个事件或一个事件跨多个读取块；只在 done 时解析成功完成 Promise。关闭页面会中止浏览器请求，服务端会话保留已持久化题目，之后可通过现有非流式重试恢复。

## 测试与验收

- Provider 测试证明流式请求携带 stream 与禁用思考，并能从 SSE 增量文本还原内容。
- 服务测试证明每个流式题目立即持久化、没有 analysis/evidence，结束后才标 extracted。
- API 测试证明响应为 text/event-stream，逐题事件先于 done，且后续 /analyze 不再调用视觉模型。
- 前端纯函数或流解析测试证明分块 SSE 会按题目递增显示，并只在 done 后解析成功。
- 真实 Kimi 试验记录首个 question SSE 事件与整页完成的耗时；该试验是性能验证，不把单次结果等同于保证时延。

## 非目标

- 不承诺 Kimi 首 token 或首题一定小于十几秒；这是模型与账号队列的外部时延。
- 不同时进行第二次非流式 Kimi 识别，也不将半截 JSON 当作可靠题目。
- 不改变 GLM 批量分析、题目编辑、证据投影或提示模式。

