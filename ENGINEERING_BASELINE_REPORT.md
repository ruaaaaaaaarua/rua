# 工程基线交付报告

审计日期：2026-09-18～19。目标是保留当前学习行为和 UI，为 AI 协作提供可执行约束和回归保护；本次没有新增产品功能。

## 1. 原项目主要风险

项目已具备有价值的测试，初始检查为 **98 项后端、45 项前端通过**，构建成功。问题不是从零缺乏测试，而是缺少贯穿日常开发与合并的工程门禁。

- 无根级 AI 工作约定、当前架构和设计体系说明；大模型容易误把历史计划当现状，误认为有独立 Question/Attempt/LearnerState 表，或顺手换状态管理/视觉风格。
- 无统一检查、lint/typecheck 配置和 CI；已有测试没有浏览器实际交互，人工容易漏跑；一个图片测试隐含依赖本机私人文件路径。
- 数据主要是 SQLite JSON；无外键/完整 JSON 约束/正式迁移；普通作答、事件与 session 更新可能跨事务；进程内锁不能支持多 worker。
- 本地单用户和 local 用户键，没有认证/授权/租户/支付；密钥明文存 SQLite 只靠文件权限。不能直接商业公网部署。
- UI 和多数业务 payload 动态类型；现有 API 多为自由 dict，OpenAPI 不是完整响应契约。隐藏解析只是 UI 折叠，普通 session 返回标准答案，不能宣称考试级防泄漏。
- Git 工作区存在用户未提交改动，无 remote，尚无可执行的远端稳定分支保护。

## 2. 增加/修改的文件与机制

| 文件 | 原因与效果 |
| --- | --- |
| `AGENTS.md` | 修改前阅读、最小 diff、禁止无关重构/UI 漂移、Protected Core、测试/迁移/review/DoD |
| `docs/ARCHITECTURE.md` | 真实模块、数据流、领域对象、全部 9 张表、允许依赖和高风险边界 |
| `docs/DESIGN_SYSTEM.md` | 固化现有字体/色板/尺寸/组件/响应断点/档案局部主题及截图策略 |
| `docs/DEVELOPMENT.md` | 安装/统一 gate、测试地图、日常模型协作、CI 设置、备份/revert、生产前置条件 |
| `ENGINEERING_BASELINE_REPORT.md` | 本交付说明和未完成边界 |
| `README.md` | 在保留用户已有编辑的基础上补工程文档与统一检查入口 |
| 根 `package.json`、`scripts/check.py` | 一个 fail-fast 的 `npm run check`；所有模型和 CI 共用，隔离真实数据 |
| `requirements-dev.txt`、`pyproject.toml` | 固定 Ruff/Mypy 开发依赖；正确性 lint、渐进类型检查、pytest 配置 |
| `web/package.json`、`web/package-lock.json` | 新增 typecheck/lint/test:e2e 命令及精确版本开发工具；现有依赖版本不变 |
| `web/tsconfig.json`、`web/eslint.config.js` | 边界模块 checkJs、全 JS/JSX 正确性/Hook 调用 lint |
| `web/vite.config.js` | 限定 Vitest 匹配 src 单元测试，避免将 Playwright 用例当 Vitest 收集；构建/代理配置不变 |
| `tests/test_engineering_core.py` | 19 个参数化回归案例，补判分/重开/调度/DB 约束/删除/旧库/API 边界 |
| `tests/conftest.py` | pytest 默认拒绝外网 TCP/DNS，避免未来测试误打真实模型服务 |
| `tests/test_images.py` | 可选 HEIC 实图改为显式 GRID_TEST_HEIC，不自动读取开发者私人图片 |
| `tests/browser_server.py` | 独立临时目录、真实 FastAPI/SQLite、假 Gateway；不动正在运行的服务 |
| `web/playwright.config.js`、`web/e2e/learning.spec.js` | 真实构建浏览器回归：两种视口，提交/重载持久化/导航/截图及失败 trace |
| `.github/workflows/check.yml` | push/PR：安装 + 同一完整检查；Ubuntu、Python 3.9/3.12、Node 24；保存浏览器证据 |
| `.github/pull_request_template.md` | 强制展示范围、回归、核心 review、UI/迁移影响和回滚说明的审阅模板 |
| `.gitignore` | 排除类型/lint 缓存和浏览器报告，避免生成产物混入提交 |

新增工具只有开发期的 Ruff、Mypy、ESLint/globals/React Hooks 插件、Playwright。没有增加生产框架、状态管理、ORM 或 UI 依赖。npm lock diff 较大来自工具的传递依赖；已用脚本对比原 lock，**现存 package 的版本变更数为 0**。

## 3. 刻意没有重构的内容

- 保留 FastAPI、React/JSX、Vite、SQLite、手写 CSS；没有足够必要性支撑更换。
- 保留 `Study.jsx`、`App.jsx`、`service.py`、`main.py` 的文件粒度；拆分能单独规划，但本次会增加回归与审阅面。
- 不改判分、知识匹配、revision、帮助污染、推荐/间隔算法；先把现有语义写清并加保护。
- 不抽出统一 Attempt 类、不制造 learner_state 表、不改 JSON 数据模型；这些会带来数据兼容性决策。
- 不引入迁移框架、强行加 FK 或改旧库；本次 schema 没有变化，先建立未来迁移规则和旧库初始化回归。
- 不自动给知识骨架填正文；18 节点仍是维护者管理的草稿。
- 不改 UI/CSS、不重排组件、不消除现有 bundle 大小警告来追求“漂亮指标”；没有新的视觉语言。
- 不做登录、支付、Docker/公网部署；它们需要明确产品与安全设计。

## 4. 核心业务覆盖

| 流程 | 本次增量 / 已有保护 |
| --- | --- |
| question retrieval | 已有 OCR 流中断重试、不重复题、题序冲突、残缺题；新增重开 app 后题目/attempt 读取 |
| answer submission / correctness | 新增 single/multiple/judge 对错矩阵，多选乱序/分隔符，非法复习答案不落库且 run 可继续提交 |
| attempt recording | 新增原答案保留、answer 事件与 attempt 一致、重启持久化；已有复习并发重复提交仅一条 |
| Question–Knowledge mapping | 新增重复 ID 去重、DB 复合 PK、非法替换保留原挂载；已有人工关联权威和公共知识不变 |
| learner state | 新增事件主键幂等、删除后个人状态/知识/藏章不再引用；已有撤销、旧诊断不进入新状态、辅助/未知帮助区别 |
| review / recommendation | 新增完整间隔曲线/封顶/错答重置、3/5/10 推荐预算不改日期、不会替其他题通过；已有上海跨日、保守分组、难度升降、帮助污染 |
| database | 新增实际 SQLite 主键/NOT NULL、integrity_check、保留/清除事件两种删除策略、旧库重复建表保留 JSON |
| API | 新增额外字段拒绝、limit 约束、Host/Origin/cross-site 与安全 header；已有密钥/内部审计脱敏、旧 revision 拒绝、流完成与失败 |
| UI | 已有 45 项纯函数/SSR/API 测试；新增桌面和移动真实浏览器提交、刷新后读取、知识/档案导航、窄屏溢出与 JS 错误检查 |

测试只证明实现满足指定契约，不证明模型学科解题准确率、提示语义完全不泄漏、无限并发或生产安全。没有以 coverage 数字代替业务证明。

## 5. 完整检查结果

根目录 **`npm run check` 已完整通过**（macOS / Python 3.9.6 / Node 24.11.1，Playwright 固定 Chromium Headless Shell 145.0.7632.6）：

| 检查 | 结果 |
| --- | --- |
| Mypy | 4 个范围内模块通过 |
| TypeScript checkJs | domain/api 通过 |
| Ruff + ESLint | 通过 |
| Knowledge validator | 18 节点、0 published，校验通过 |
| pytest | **116 passed，1 skipped**；跳过的是显式 opt-in 的 macOS HEIC 实图 |
| Vitest | **6 文件，45 项通过** |
| Vite build | 通过；保留既有 >500 kB chunk 提示 |
| Playwright | **2 项通过**：1440×1000 与 390×844；截图输出至 HTML report |
| Git diff whitespace | `git diff --check` 通过 |

初次 Playwright 下载器停滞，后用官方同版本 headless-shell 下载地址完成安装；最终 gate 使用默认固定 Chromium，无 fallback 环境变量，无跳过浏览器阶段。检查中为移动菜单增加了收起动画完成断言，避免把过渡帧作为审阅截图。

初始后端 98 项中含自动寻找私人 HEIC 的测试；现在是原 97 个常规案例 + 19 个新增案例通过，原 HEIC 案例改为可选且默认跳过。这个变化不是删除失败测试。

CI 文件已建立，但本地没有 remote，**未远端执行 GitHub CI，也未验证 Linux/Python 3.12 的实际运行结果**。不能把本机完整检查冒称远端或生产验证。生成报告位于 `web/playwright-report/index.html`，完整最终命令日志位于本机 `/tmp/grid-engineering-check.log`（临时日志不会提交）。

## 6. 仍然存在的风险与优先级

| 优先级 | 风险 | 后续处理 |
| --- | --- | --- |
| 上公网前阻断 | 无认证/授权/租户隔离，模型配置含明文密钥 | 独立设计服务端身份/隔离/secret 管理；不可只放宽 local_guard |
| 多进程前阻断 | jobs/locks/rate budget/恢复逻辑进程内 | 明确单进程运行；扩容前设计持久化任务/并发控制并测试 |
| 数据演进前阻断 | 无正式 migration，JSON 缺强约束；部分写入跨事务 | 编号迁移、版本记录、旧数据/失败恢复；先缩小事务不一致风险 |
| 数据可靠性 | 普通 retry 无请求幂等 key，网络重试可被记多次；备份未自动化 | 专项请求幂等设计；真实恢复演练（本次未操作用户库） |
| 合并治理 | 无 remote，无法启用稳定分支 required checks/审批 | 连接远端后按 DEVELOPMENT 设置 ruleset；CI 文件本身不能强制阻止管理员合并 |
| 静态检查边界 | Python 仅 4 模块类型检查；JS 仅 domain/api、strict=false；React/动态 payload 未严格类型化 | 新模块逐步加入；禁止把 gate 成功描述为全仓类型安全 |
| UI | 截图仅审阅证据，无像素 diff；目前只有两视口一个关键流程 | 固定 Linux/字体环境人工审阅少量 golden 后接入截图比较 |
| 供应链 | Python 传递依赖未完整锁定/哈希校验；GitHub Actions 使用 major tag | 生产流水线建立依赖锁、漏洞策略和 Action SHA 更新流程 |
| 性能 | 多处扫描全部 session/事件，N+1 查询；前端约 700 kB 主 JS | 以真实规模 profiling 后专项优化，不顺手改架构 |
| 模型质量 | 结构化输出/引用不等于正确；提示正则不能保证语义不泄漏 | 建立独立学科评测与人工审核，避免把模型结论当可信规则 |
| 部署/平台 | start.command 只在缺 dist 时构建；HEIC 转码仅 macOS | 发布显式重建；Linux 图片能力另立需求；新生产环境不要采用旧 Python 3.9 |

## 7. 模型任务分工

这是项目的风险分配约定，不是关于某个模型能力的绝对承诺；所有模型共用同一 gate。

| 执行者 | 适合任务 | 边界 |
| --- | --- | --- |
| GLM | 已写清验收的小范围文案/文档修订、fixture、已有组件的局部需求、纯函数 bug 的最小修复 | 明确允许文件；遵循设计约束；涉及核心则升级 review，不能自行扩大重构 |
| GPT-5.6 | 普通跨文件页面/API 调用接线、错误处理、测试补全、已有模式下的维护 | 同样先识别 Protected Core；不能以模型名代替测试或独立审阅 |
| 高能力模型 / senior reviewer | 领域状态机、判分、映射/图、并发/事务、迁移、API 安全、认证/授权、支付设计；复杂故障复盘；核心 PR 独立 review | 先确定不变量与失败恢复，再实现；权限、支付、不可逆数据决策由人负责批准 |

低风险实现不需要每次都让高能力模型重写；提高模型等级时也应审阅最小 diff，不重新设计整个系统。

## 8. Git 状态与回滚

起点/交付工作分支为 `codex/power-study-workspace`，起点 HEAD `6418390`。原历史保持不变；未 reset、rebase、force-push、自动 commit/tag 或切换分支。真实 data 目录和运行中的服务未用于本次测试。

开始时已有改动：README、app/service.py、docs/superpowers/plans/2026-09-16-learning-frontend-brief.md、tests/test_personal_backend.py、web/src/Archive.test.jsx、web/src/archive.js；以及未跟踪的 2026-09-17 personal-learning acceptance/progress 文档。本次仅在 README 增补工程入口，其余已有 diff 已逐文件比对保留。报告不把这些原有业务修复算作本次成果。

本次未自动提交，避免将用户已有工作混入工程基线。后续按 README hunk + 表中新增/修改文件显式暂存，查看 cached diff，形成独立基线 commit；原有工作单独处理。未来功能用 codex/feature 分支；发布只对已验证 commit 打 annotated tag；共享历史回滚用 revert。数据/schema 改动必须另有备份恢复方案，不能只 revert 代码。

## 9. 每天使用的方法

读规则和目标模块 → 检查 Git/分支 → 明确验收及允许改动文件 → 先补失败回归 → 最小实现 → 看 diff → `npm run check` → Protected Core 独立 review / UI 截图检查 → 独立 commit / PR → required CI 成功后合并。

可直接交给普通开发模型：

> 先读 AGENTS.md 和相关架构/测试。仅完成本需求，允许修改文件为……；保持既有行为和 UI，不顺手重构。验收为……。发现核心影响先说明不变量与测试，完成后执行 npm run check，报告文件、结果、风险。

完整命令、测试地图、远端保护设置和恢复步骤见 `docs/DEVELOPMENT.md`。
