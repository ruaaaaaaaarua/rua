# Power Study Workspace Implementation Plan

**Goal:** 实现电力系统分析 Wiki、个人题目挂载和事实驱动复习，重做学习工作台。

**Architecture:** 保持现有本地 FastAPI/SQLite 应用，知识内容与个人事件分层。保留模型连接协议、重试和流式识别；移除推断诊断与生成测验。

**Tech Stack:** Python/FastAPI/Pydantic/SQLite，React/Vite，现有 Markdown/KaTeX/Lucide。

## Global Constraints

- 科目仅电力系统分析；知识正文不预填；稳定 ID 不随名字变化。
- 旧数据与模型密钥保留；不对外发布，不自动调用用户付费模型作测试。
- 不保留自动错因诊断、生成练习、掌握率、要求用户输入思路/信心的活跃流程。
- 只把真实事件用于状态；照片答案帮助情况未知；草稿内容不作为知识引用。
- 原题复习明确标记；查看答案后通过不能算独立；争议或修改使依赖判断失效。

## Tasks

- [x] 核心知识与个人记录：新增 app/knowledge.py、app/study.py、knowledge/catalog.json 和正文模板；编写目录校验/个人关联/复习规则测试。
- [x] 模型和 HTTP 流程：收敛 app/service.py、app/models.py、app/prompts.py、app/providers.py、app/main.py，使用已发布 Wiki 上下文，删除生成与诊断端点，兼容旧设置。
- [x] 工作台界面：按 docs/superpowers/plans/2026-09-15-frontend-brief.md 实现三个页面、设置与题目编辑；前端构建与测试。
- [x] 集成验证与文档：更新 README 和知识填充说明，替换旧功能测试并保留连接/上传回归；浏览器验证桌面/移动端；交付可直接启动的版本。独立审阅因子代理额度不可用未完成，主代理完成代码复核与回归测试，不将其记为独立审阅通过。

## 验证记录（2026-09-15）

- Python：47 tests passed；前端：11 tests passed；Vite production build 成功。
- 知识目录校验：6 章节、18 节点、0 已发布正文；没有预填题库或学科正文。
- 浏览器：桌面/390px 手机布局、知识详情空态、原题作答、辅助复习、多个知识点挂载；最终构建无浏览器 error/warn。
- 回归修正：中断识别按题目签名核对，拒绝静默跳过变化题目；普通识别复用流式缓存；复习与同会话编辑/讲解串行；旧 hint 入口移除。
- 付费模型：未调用。模拟测试只证明工作流，不证明识图/学科解题准确率。
- 数据：启动前 SQLite 备份为 data/backups/pre-power-study-20260915.sqlite3，integrity_check 为 ok；原图与模型配置保留。样例联调服务已关闭，正式本地服务已启动。
- 已知边界：本地单用户，无远程 MCP/付费/账户；构建存在单包大于 500kB 的体积提示，不影响本地启动。后续可做按页/公式模块拆包。
