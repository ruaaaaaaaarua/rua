# 渐进式图片识别展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Kimi 图片识别完成后立即显示题目与作答，并自动继续 GLM 的批量解题和诊断。

**Architecture:** 从 `LearningService.analyze()` 中拆出可单独调用的 `extract()` 阶段。前端上传后先请求提取接口、渲染已识别题目；React effect 在这次渲染后自动调用保留的分析接口。所有阶段先写入 SQLite，再返回浏览器。

**Tech Stack:** Python 3.9、FastAPI、Pydantic、SQLite、pytest、React 19、Vite、Vitest。

## Global Constraints

- 图片识别继续使用配置的 `vision` 模型；独立解题和诊断继续使用 `solve` 模型。
- 不改变独立解题的学生作答隔离、批量分析、单题降级、答案泄露保护或知识证据规则。
- 仅识别阶段不得创建答案、对错结论、分析或学习证据。
- GLM 分析失败后必须保留已识别题目；重试不得再次调用 Kimi。
- 不新增后台任务、SSE/WebSocket 或外部队列；同一会话仍只有一个模型操作。
- 只暂存和提交本计划产生的文件；不能覆盖工作树中已有的未提交批量分析改动。

---

## 文件结构

- `app/service.py`：图片识别与整页分析编排。
- `app/main.py`：锁保护的提取 API。
- `tests/test_evidence_boundaries.py`：视觉调用、分析调用和证据边界。
- `tests/test_api.py`：端点与恢复契约。
- `web/src/api.js`：提取请求。
- `web/src/domain.js` 和 `web/src/domain.test.js`：阶段显示/续跑的纯逻辑。
- `web/src/App.jsx`：上传、即时渲染和自动续跑。
- `README.md`：用户可见行为说明。

### Task 1: 仅识别服务阶段

**Files:**

- Modify: `tests/test_evidence_boundaries.py:151-188`
- Modify: `app/service.py:59-149`

**Interfaces:**

- Consumes: `gateway.extract(images) -> list[dict]`、附件 `extracted` 标记、`Store.save_session(session)`。
- Produces: `async LearningService.extract(session: dict) -> dict`；成功时返回 `status == 'extracted'`、已持久化题目且无分析。

- [ ] **Step 1: 写失败测试，固定识别的边界**

在 `tests/test_evidence_boundaries.py` 添加一个记录调用次数的网关。为临时会话写入一个 PNG 附件，调用 `service.extract(session)`。断言视觉调用为 1、解题和诊断调用均为 0、附件标为 extracted、会话为 extracted、返回题目无 `analysis`，且 `store.knowledge() == []`：

```python
def test_extract_persists_questions_without_analysis_or_evidence(tmp_path):
    class VisionOnly(Gateway):
        extracts = solves = diagnoses = 0
        async def extract(self, images):
            type(self).extracts += 1
            return await Gateway.extract(self, images)
        async def solve(self, question):
            type(self).solves += 1
            return await Gateway.solve(self, question)
        async def diagnose(self, question, solution, history):
            type(self).diagnoses += 1
            return await Gateway.diagnose(self, question, solution, history)

    store = Store(tmp_path)
    session = store.create_session()
    store.attachments.joinpath('image').write_bytes(b'png')
    session['attachments'] = [{
        'id': 'image', 'name': 'page.png', 'mime': 'image/png', 'extracted': False
    }]
    store.save_session(session)

    result = asyncio.run(LearningService(store, lambda _: VisionOnly()).extract(session))

    assert result['status'] == 'extracted'
    assert result['attachments'][0]['extracted'] is True
    assert result['questions'] and 'analysis' not in result['questions'][0]
    assert (VisionOnly.extracts, VisionOnly.solves, VisionOnly.diagnoses) == (1, 0, 0)
    assert store.knowledge() == []
```

- [ ] **Step 2: 确认测试正确失败**

Run: `.venv/bin/python -m pytest tests/test_evidence_boundaries.py::test_extract_persists_questions_without_analysis_or_evidence -q`

Expected: FAIL，因为 `LearningService.extract` 不存在。

- [ ] **Step 3: 实现最小提取阶段**

在 `LearningService` 增加下列方法；它只遍历未提取的非参考、未删除附件。每张成功后立即保存，失败时保留前面成功的附件。空输入沿用 `analyze` 的 ValueError，demo 直接返回。

```python
async def extract(self, s):
    if s.get('demo'):
        return s
    if not s['attachments'] and not s['questions']:
        raise ValueError('请先上传已作答的题目图片。')
    s.update(status='recognizing', error=None)
    self.store.save_session(s)
    gateway = self.gateway()
    for attachment in s['attachments']:
        if attachment.get('reference') or attachment.get('extracted') or attachment.get('deleted'):
            continue
        blob = (self.store.attachments / attachment['id']).read_bytes()
        data_url = 'data:' + attachment['mime'] + ';base64,' + base64.b64encode(blob).decode()
        for question in await gateway.extract([{'data_url': data_url, 'name': attachment['name']}]):
            question.update(id=uid(), attachment_id=attachment['id'], revealed=False)
            self.canonicalize(question)
            s['questions'].append(question)
        attachment['extracted'] = True
        self.store.save_session(s)
    s.update(status='extracted', error=None)
    self.store.save_session(s)
    return s
```

将 `analyze` 原先的附件循环替换为：

```python
if any(not a.get('reference') and not a.get('extracted') and not a.get('deleted') for a in s['attachments']):
    await self.extract(s)
gateway = self.gateway()
s.update(status='analyzing', error=None)
self.store.save_session(s)
```

不要修改后面的 `merge`、批量解题、批量诊断、单题降级或 evidence 逻辑。

- [ ] **Step 4: 确认提取测试转绿**

Run: `.venv/bin/python -m pytest tests/test_evidence_boundaries.py::test_extract_persists_questions_without_analysis_or_evidence -q`

Expected: PASS。

- [ ] **Step 5: 写失败测试，固定分析恢复**

再添加一个记录 `extract`、`solve_batch` 和 `diagnose_batch` 次数的网关。先调用 `extract(session)`，再调用 `analyze(session)`。断言视觉调用仍为 1、批量解题和批量诊断各为 1、会话 ready、题目 confirmed、知识证据数为 1：

```python
def test_analyze_after_extract_skips_vision_and_records_evidence(tmp_path):
    # 创建带一个附件的会话与具备 solve_batch/diagnose_batch 的计数网关。
    # await service.extract(session); await service.analyze(session)。
    # 断言 extracts == 1、batch_solves == 1、batch_diagnoses == 1、
    # result['status'] == 'ready'、store.knowledge()[0]['evidence_count'] == 1。
    ...
```

- [ ] **Step 6: 确认恢复测试失败后转绿**

Run: `.venv/bin/python -m pytest tests/test_evidence_boundaries.py::test_analyze_after_extract_skips_vision_and_records_evidence -q`

Expected before Step 3: FAIL；after Step 3: PASS，因为 `analyze` 只对未提取附件调用 `extract`。

- [ ] **Step 7: 运行服务回归**

Run: `.venv/bin/python -m pytest tests/test_evidence_boundaries.py tests/test_learning.py -q`

Expected: PASS。

### Task 2: 提取 API 与分析恢复契约

**Files:**

- Modify: `tests/test_api.py:24-110`
- Modify: `app/main.py:218-220`

**Interfaces:**

- Consumes: `service.extract(session)` 和既有 `operation(sid, fn)`。
- Produces: `POST /api/sessions/{sid}/extract`，返回公共的 extracted 会话；现有 `/analyze` 仍支持旧的一步式调用。

- [ ] **Step 1: 写端点失败测试**

在 `tests/test_api.py` 使用已有注入 Gateway 的 TestClient：创建会话、上传合法 PNG、POST `/extract`，断言 HTTP 200、状态 extracted、题目存在且没有 analysis；再 POST `/analyze`，断言状态 ready 且问题已有 analysis：

```python
def test_extract_endpoint_returns_questions_before_analysis(client):
    app, http = client
    session = http.post('/api/sessions').json()
    assert http.post(
        f"/api/sessions/{session['id']}/upload",
        files={'files': ('page.png', b'\x89PNG\r\n\x1a\nbody', 'image/png')},
    ).status_code == 200

    extracted = http.post(f"/api/sessions/{session['id']}/extract")
    assert extracted.status_code == 200
    assert extracted.json()['status'] == 'extracted'
    assert extracted.json()['questions'] and 'analysis' not in extracted.json()['questions'][0]

    analyzed = http.post(f"/api/sessions/{session['id']}/analyze")
    assert analyzed.status_code == 200
    assert analyzed.json()['status'] == 'ready'
    assert analyzed.json()['questions'][0]['analysis']['status'] == 'confirmed'
```

- [ ] **Step 2: 确认端点测试正确失败**

Run: `.venv/bin/python -m pytest tests/test_api.py::test_extract_endpoint_returns_questions_before_analysis -q`

Expected: FAIL with HTTP 404。

- [ ] **Step 3: 添加最小路由**

在 `/analyze` 路由前添加：

```python
@app.post('/api/sessions/{sid}/extract')
async def extract(sid: str):
    return await operation(sid, service.extract)
```

不修改 `operation`；它已经负责会话互斥、错误脱敏和 `public_session`。

- [ ] **Step 4: 验证 API 和后端完整回归**

Run: `.venv/bin/python -m pytest tests/test_api.py::test_extract_endpoint_returns_questions_before_analysis -q && .venv/bin/python -m pytest -q`

Expected: 全部 PASS。

### Task 3: 前端即时识别结果与自动续跑

**Files:**

- Modify: `web/src/domain.test.js:1-38`
- Modify: `web/src/domain.js`
- Modify: `web/src/api.js:12-20`
- Modify: `web/src/App.jsx:12,29-36,78-88`

**Interfaces:**

- Consumes: `api.extract(id) -> session(status: 'extracted')` 和 `api.analyze(id)`。
- Produces: `analysisStage(status)`、`shouldResumeAnalysis(status)`；上传后已识别题目先渲染，随后只对 extracted 会话自动开始分析。

- [ ] **Step 1: 写前端纯函数失败测试**

在 `web/src/domain.test.js` 添加导入和以下测试：

```javascript
import { analysisStage, shouldResumeAnalysis } from './domain.js'

describe('analysisStage', () => {
  it('distinguishes recognition from post-recognition analysis', () => {
    expect(analysisStage('recognizing')).toEqual({
      active: true, title: '正在识别图片', detail: '正在提取题目、选项和你的作答。'
    })
    expect(analysisStage('extracted')).toEqual({
      active: true, title: '题目已识别，正在独立解题', detail: '已显示识别内容；答案与诊断将随后补齐。'
    })
    expect(analysisStage('analyzing').title).toBe('正在独立解题与诊断')
  })
})

describe('shouldResumeAnalysis', () => {
  it('only resumes a persisted extracted session', () => {
    expect(shouldResumeAnalysis('extracted')).toBe(true)
    expect(shouldResumeAnalysis('recognizing')).toBe(false)
    expect(shouldResumeAnalysis('analyzing')).toBe(false)
    expect(shouldResumeAnalysis('ready')).toBe(false)
    expect(shouldResumeAnalysis('error')).toBe(false)
  })
})
```

- [ ] **Step 2: 确认前端测试正确失败**

Run: `npm --prefix web test -- domain.test.js`

Expected: FAIL，因为两个导出不存在。

- [ ] **Step 3: 实现阶段纯函数**

在 `web/src/domain.js` 增加：

```javascript
const ANALYSIS_STAGES = {
  recognizing: { active: true, title: '正在识别图片', detail: '正在提取题目、选项和你的作答。' },
  extracted: { active: true, title: '题目已识别，正在独立解题', detail: '已显示识别内容；答案与诊断将随后补齐。' },
  analyzing: { active: true, title: '正在独立解题与诊断', detail: '正在核对整页作答并整理简短反馈。' },
}
export const analysisStage = status => ANALYSIS_STAGES[status] || { active: false, title: '', detail: '' }
export const shouldResumeAnalysis = status => status === 'extracted'
```

- [ ] **Step 4: 验证纯函数测试转绿**

Run: `npm --prefix web test -- domain.test.js`

Expected: PASS。

- [ ] **Step 5: 接入阶段 API 与页面**

在 `web/src/api.js` 增加：

```javascript
extract: (id) => request(`/sessions/${id}/extract`, json('POST', {})),
```

在 `App.jsx` 执行下列精确修改：

1. 将 `recognizing` 和 `extracted` 加入 `PROCESSING`。
2. 导入 `analysisStage` 与 `shouldResumeAnalysis`；Overview 空结果面板使用 `analysisStage(session.status)` 的 title/detail，不再固定显示“正在识别和分析整页”。未分析题目不能显示对错、答案或虚构诊断。
3. 把上传链改为 `api.upload(current.id, list).then(() => api.extract(current.id))`，成功时 `update(extractedSession)` 后清空选择题目。
4. 在 App 内增加 effect：`session?.status === 'extracted'` 且 `busy === false` 时用 `setTimeout(..., 0)` 调用 `run(() => api.analyze(session.id), update)`；effect cleanup 必须 `clearTimeout(timer)`。请求开始后服务端状态为 analyzing；失败后状态 error，effect 不循环重试；刷新后重新打开 extracted 会话会再次恢复。

- [ ] **Step 6: 验证前端**

Run: `npm --prefix web test && npm --prefix web run build`

Expected: 所有 Vitest 测试 PASS，生产构建无导入或语法错误。

### Task 4: 文档、真实流程验收与差异检查

**Files:**

- Modify: `README.md:19-23`（只增加用户可见的阶段说明）

**Interfaces:**

- Consumes: Task 1–3 的提取端点、状态和前端续跑。
- Produces: 已通过自动化和本地 HTTP 检查的渐进上传体验。

- [ ] **Step 1: 增加用户说明**

在 README 的“第一次使用”上传步骤后加入：

```markdown
上传后会先显示识别出的题目和作答，随后自动补齐独立解题与诊断；图片识别或后续分析失败时，已成功保存的阶段可以单独重试。
```

- [ ] **Step 2: 运行最终检查**

Run: `.venv/bin/python -m pytest -q && npm --prefix web test && npm --prefix web run build && git diff --check`

Expected: pytest、Vitest、构建和 diff 检查全通过。

- [ ] **Step 3: 进行手工 HTTP/页面验收**

Run: `.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765`

Expected: 上传真实图片后，Kimi 识别完成时能显示题目与作答；随后页面自动进入 GLM 分析；结果补齐。若 GLM 失败，刷新后仍看到题目并可手动重试，且 Kimi 不重复调用。

- [ ] **Step 4: 创建聚焦提交**

先检查现有差异归属；只有目标文件没有混入既有未提交改动时才执行：

```bash
git add README.md app/main.py app/service.py web/src/api.js web/src/domain.js web/src/domain.test.js web/src/App.jsx tests/test_api.py tests/test_evidence_boundaries.py
git commit -m "feat: show recognized questions before analysis"
```

若 `app/service.py`、测试文件或其他目标文件包含本任务前已有的混合差异，不提交，向用户报告确切文件和原因。

## Plan self-review

- Spec coverage: Task 1 覆盖阶段拆分、持久化和证据边界；Task 2 覆盖 API 与恢复；Task 3 覆盖先渲染再续跑和状态文案；Task 4 覆盖文档、自动化、真实使用和差异安全。
- Placeholder scan: 没有未定项、待补内容或含糊的后置开发描述；每段实现步骤都给出接口、断言和命令。
- Type consistency: 服务为 `extract(session)`，路由调用 `service.extract`，浏览器调用 `api.extract(id)`；阶段名始终为 `recognizing`、`extracted`、`analyzing`、`ready`、`error`。
