# AI coding 工程约定

适用于整个仓库及所有模型。目标：保留当前业务行为和视觉，以最小可审阅改动完成明确需求。

## 修改前

1. 阅读 `README.md`、`docs/ARCHITECTURE.md`、`docs/DEVELOPMENT.md`；涉及 UI 再读 `docs/DESIGN_SYSTEM.md`；首次接手读 `ENGINEERING_BASELINE_REPORT.md`。
2. `git status --short --branch`、`git diff --stat`，检查已有未提交内容。不要覆盖、回退、提交其他人的改动。历史计划仅是背景，当前代码与已确认需求是依据。
3. 阅读目标模块的调用方、数据写入方及对应测试；先说明要改哪些文件、为什么、哪些不变量会受影响。错误修复应先用失败测试复现。
4. 只在临时数据目录测试；不得使用用户的 `data/`、模型密钥或真实模型额度作为自动化 fixture。

## Minimum Diff Principle

- 一次需求对应一个可独立 revert 的改动；只改必要文件。禁止顺手重命名、搬文件、格式化全仓库、清理无关代码、升级无关依赖。
- 不得自行更换框架、数据库、状态管理、路由、依赖方向或领域模型。需求确需架构变化时先提交具体设计、兼容策略、验证方法供项目负责人审阅，再实现。
- **未经需求明确要求，不得改变 UI、交互默认值或全局视觉语言。** 复用 `ui.jsx`、现有 CSS 类和变量；禁止新增第二套设计系统。需求范围内的必要小修复可以直接推进，不需反复确认。
- 发现无关问题，记入交付说明；除非直接阻塞当前验收，不扩大任务范围。
- 不通过删测试、放宽断言、添加 `skip`、`noqa`、`@ts-nocheck` 或缩小检查范围让 CI 变绿。

## Protected Core：改动必须补测试并接受更严格 review

| 核心 | 实际位置 |
| --- | --- |
| 判分、识别完整性、作答/帮助事实、revision 撤销 | `app/models.py`、`app/store.py:normalized_answer`、`app/service.py` |
| Question–Knowledge mapping、事件投影、复习间隔/推荐 | `app/study.py`、`app/classification.py`、`app/personal.py`、`app/archive.py` |
| Knowledge graph / 发布边界 | `app/knowledge.py`、`knowledge/catalog.json`、`knowledge/nodes/` |
| 数据表/JSON 数据格式/未来 migrations | `app/store.py`、`app/study.py`、`app/archive.py` 及未来迁移脚本 |
| API 输入/输出、密钥脱敏、本机访问限制 | `app/main.py`、`app/service.py:public_session`、`web/src/api.js` |
| 模型契约、提示上下文、防泄漏、重试/并发 | `app/providers.py`、`app/prompts.py`、`app/jobs.py` |
| 前端请求竞争、流式合并、答题/分类输入 | `web/src/App.jsx`、`web/src/domain.js`、`web/src/Study.jsx` 中相关逻辑 |
| 认证、授权、租户隔离、支付 | **当前不存在**；未来一旦引入默认属于 Protected Core |

这些区域的修改须说明不变量、失败/重试/旧数据场景，增加或更新针对性测试，并由非实现者的高能力模型或资深工程师独立 review。文档/注释改动无需伪造业务测试，但仍检查事实与运行完整 gate。付款、租户/权限、不可逆迁移最终由人负责批准。

必须保留：未作答不是答错/答对；pending/残缺题不产生有效证据；原始作答不被重答覆盖；已获得帮助不会因题目修订消失；撤销的事件不进入状态/藏章；旧 revision 复习不能提交；复习重复提交仅落一条事实；推荐不替同组其他题通过；草稿不进入教学上下文；AI 不写公共知识；解题不迎合个人历史答案。

## 测试与迁移

- 业务行为、API 契约、并发/时间逻辑、安全边界、持久化、修复 bug：必须有能证明结果的回归测试。纯文档/无行为注释不强求新测试。
- API/领域跨层变化用真实临时 SQLite + 模拟 Gateway 集成测试；页面交互变化更新少量 Playwright 测试。UI 变化提供桌面/移动截图，不得盲目更新基线。
- 当前没有迁移框架：建表在构造函数里，JSON 没有全局版本；`analysis.schema_version=3` **不是数据库版本**。不得静默重建数据库、丢弃未知 JSON 字段或批量覆写历史。
- 未来 schema 改动必须提交编号、可重复执行的迁移与版本记录，旧库 fixture、重复执行/失败回滚测试、备份与恢复方法。先证明必要性，再选择最小机制，不默认引入 ORM。
- 数据迁移前停止写入并备份整个数据目录；代码 revert 不等于数据回滚。不能验证可恢复性就不能声称可安全发布。

## 必跑检查和 Definition of Done

根目录执行 **`npm run check`**（安装方法见 `docs/DEVELOPMENT.md`）。它运行渐进类型检查、全代码正确性 lint、知识校验、后端/前端测试、构建、真实浏览器测试。不得跳过失败阶段宣称完成。

完成必须满足：

1. 明确需求实现，diff 范围合理，现有行为/UI 保留或差异得到需求授权。
2. 适用的回归测试通过；Protected Core 获得独立 review；边界变化同步文档。
3. 完整 gate 成功；若环境阻塞，明确失败命令/原因，不能标为通过。
4. `git diff --check`；检查无密钥、个人数据库、图片、生成构建文件进入提交。
5. 交付修改文件、原因、测试结果、剩余风险及回滚方式。使用明确路径分批暂存；禁止 `git add .` 混入已有工作。
6. PR 进入稳定分支前 CI 必须通过且风险审阅完成。不得自行 force-push、reset --hard、清理用户文件或发布生产。

模型分工按风险而非名称决定：GLM 可做范围明确的小改与 fixture；GPT-5.6 可承担跨文件普通实现和回归补充；高风险核心/迁移/并发/权限设计交高能力模型设计或 review。任何模型均不能豁免本约定。
