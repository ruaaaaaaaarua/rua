# 开发、验证和发布前置条件

## 一次性安装

已在 macOS / Python 3.9.6 / Node 24.11.1 验证；CI 另跑 Ubuntu / Python 3.9、3.12 / Node 24。日常建议采用 CI 工具链；Python 3.9 仅保留现有兼容性测试，不作为新生产环境选型。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix web ci
cd web
npx --no-install playwright install chromium
cd ..
npm run check
```

Linux 安装浏览器系统依赖用 `npx --no-install playwright install --with-deps chromium`。没有真实模型调用、密钥或个人数据要求。Playwright 占用独立 18765 端口，若已占用应失败，不得终止/复用未知服务。原有 Vite 5173、后端 8765 不受影响。

根 package.json 仅提供命令入口，没有另一份 Node 依赖树；不需要根目录 npm install。前端使用已提交的 package-lock.json，CI 用 npm ci；新增依赖须精确锁版本、说明必要性并审阅 lock diff。Python 顶层依赖已锁定，传递依赖尚未完整锁定/哈希校验，见剩余风险。

## 统一 gate

**所有修改最终运行根目录 `npm run check`**。`scripts/check.py` 优先用 .venv，CI 无 .venv 时使用当前 Python；可用 CHECK_PYTHON 指定绝对路径。失败立即停止并返回非零，不自动安装依赖、不修改业务文件、不连接用户数据库。

| 顺序 | 命令 | 当前真实覆盖范围 |
| --- | --- | --- |
| 1 | `.venv/bin/python -m mypy` | models、knowledge、images、prompts 四个模块；check_untyped_defs；导入模块 silent |
| 2 | `npm --prefix web run typecheck` | TypeScript checkJs 检查 domain.js、api.js；noEmit、strict=false |
| 3 | `.venv/bin/python -m ruff check app tests scripts` | 全后端/测试/脚本，E9/F63/F7/F82 正确性规则，非格式大扫除 |
| 4 | `npm --prefix web run lint` | 全 JS/JSX，未定义变量、重复 key、不可达代码、错误 optional chaining、Hook 调用规则等 |
| 5 | `.venv/bin/python -m app.validate_knowledge` | 实际知识目录、路径、发布正文、来源及关系完整性 |
| 6 | `.venv/bin/python -m pytest -q` | 后端单位/集成/并发回归，临时 SQLite、模拟模型 |
| 7 | `npm --prefix web test` | 纯函数、前端请求/SSE、SSR 可见性与交互状态 |
| 8 | `npm --prefix web run build` | 真实生产前端产物；保留原 Vite 警告，不掩盖 |
| 9 | `npm --prefix web run test:e2e` | Chromium、真实 built UI → HTTP → 临时 SQLite，桌面/移动 |

这是**渐进静态检查**，不是全仓严格类型安全：JS 的动态 JSON 仍含 any，React 页面未纳入 checkJs，主要 Python 编排与存储模块没有全面类型检查；不启用所有格式/unused/exhaustive-deps 规则以免引发无关重写。改这些边界仍需业务回归与 review。后续新增独立纯模块应在同一 PR 加入类型检查范围；既有模块的类型治理单独立项，不能降低当前范围。

新增测试要证明不变量/故障结果，不能只测试内部实现或追求 coverage 百分比。不接受网络服务不稳定导致长期重试绿灯。当前核心回归地图：

| 业务链路 | 主要测试 |
| --- | --- |
| 题目获取/OCR、断流缓存、顺序变化、残缺题 | test_api、test_progressive、test_progressive_providers |
| 判分、提交、原答案保留、持久化重开 | test_api、test_engineering_core、test_providers |
| 知识匹配/关系/发布/个人可见边界 | test_learning、test_personal_backend、test_engineering_core |
| 有效事件、重复提交、revocation、帮助污染 | test_evidence_boundaries、test_interactions、test_engineering_core |
| 1/3/7/14/30 调度、上限/错答重置、上海跨日、推荐 | test_personal_backend、test_engineering_core |
| 约束、删除、幂等建表、旧 JSON 保留 | test_engineering_core |
| API 错误码/严格输入/脱敏/本机防护 | test_api、test_personal_backend、test_engineering_core、web/src/api.test.js |
| UI 语义、流式合并、表单恢复/分享 | web/src 的 6 个 Vitest 文件 |
| 浏览器复习提交、重载持久化、导航/窄屏 | web/e2e/learning.spec.js |

`test_images` 的真实 HEIC 验证需要显式 GRID_TEST_HEIC 路径且为 macOS；默认跳过，避免读取开发者私人图片。跨平台格式/文件头校验正常运行。它不证明 Linux 支持 HEIC 转码。

E2E 临时服务器在 `tests/browser_server.py`，使用固定测试题、模拟 Gateway、TemporaryDirectory；不复用生产进程。由于现有 Origin 白名单只允许 8765/5173，**测试服务器专用** middleware 仅把精确的 `http://127.0.0.1:18765` Origin 映射为允许的 5173 Origin；生产 middleware 与 API 返回/业务逻辑均不改，浏览器不 mock 响应。Host/Origin/cross-site 防护由 pytest 对生产 create_app 单独验证，此 E2E 不等同完整网络安全测试。每个视口用独立 session，防止彼此帮助记录污染。

报告在 `web/playwright-report/`、`web/test-results/`，均忽略提交；CI 保存 7 天。截图策略见 DESIGN_SYSTEM.md。若安装 Chromium 的 CDN 不可达，可显式设 `PLAYWRIGHT_CHANNEL=chrome` 用本机已安装 Chrome 的独立临时浏览器 profile 验证；必须报告该环境差异，CI 仍默认锁定 Playwright Chromium。不能用已有用户浏览器会话跑测试。

## 日常开发步骤

1. 读 AGENTS 与目标模块，检查 Git 状态，划定需求、允许文件与验收用例。
2. 干净基线新开 `codex/<task>` feature branch；有未提交工作先保留/辨认归属，不能自动 stash/reset。普通任务保持可在一次 review 中理解。
3. 给模型明确输入：需求、允许文件、禁止变化、相关测试、不变量、完成命令。遇到架构/核心改变升级给高能力 reviewer，不靠增加模型并发解决边界不清。
4. 业务 bug 先失败测试；实现最小改动；检查小范围 `git diff -- path/to/file`。
5. 完整 gate + `git diff --check`；UI 变更看桌面/移动截图；核心改动进行独立 review，修复后重跑受影响检查及最终 gate。
6. 显式 `git add <files>` 或 `git add -p`，用 `git diff --cached` 确认只含本需求；一个逻辑改动一个 commit；PR 填模板。
7. CI 成功且 review 通过后合并。稳定 commit 可 `git tag -a baseline-YYYYMMDD -m 'verified baseline' <commit>`；不把未验证工作区当稳定版本。

任务说明模板：

```text
需求/复现：...
允许修改：...
必须保留：业务规则、API 合约、当前 UI；不顺手重构
验收：...
相关测试：...
Protected Core：是/否；是则列不变量和 reviewer
完成：npm run check；文件/原因/结果/风险
```

## CI 与稳定分支保护

`.github/workflows/check.yml` 在所有 push、pull_request、手动触发运行；无路径过滤，避免文档/配置变更绕过 gate。install → type/lint/knowledge/tests/build/browser 同一入口，20 分钟超时、最小 contents:read 权限、同分支旧任务自动取消。

**workflow 本身不能禁止合并。** 仓库管理员需在远端 ruleset/branch protection 中对稳定分支设置：要求 PR、至少一个独立审批、禁止 force-push/delete、要求最新分支上的 `check (Python 3.9)` 和 `check (Python 3.12)` 成功（以 GitHub 首次运行实际显示名为准）；核心 PR 由指定资深 reviewer 审阅。当前无 Git remote，无法在本地配置/验证该服务器规则，也无法声称 CI 已远端执行。绑定团队后再加真实 CODEOWNERS，不能虚构账号。

## 回滚、备份与生产准备

共享历史用 `git revert <commit>` 产生反向提交，不 reset/rebase 已共享历史；恢复后重跑 check、重新构建 dist、停止旧服务再重启。start.command 不自动刷新已有 dist，不能只 checkout 代码就声称回滚完成。

当前无新 schema，因此本次基线不需要迁移。未来数据变更之前停止**所有**写入进程，把整个 GRID_LEARNING_DATA 目录复制到新的时间戳备份位置（含 sqlite/WAL/SHM/attachments）；备份不得入 Git 或 CI artifact。先在副本验证 `PRAGMA integrity_check`、数据条数、原图和核心流程，再用副本演练恢复。不要将 sqlite 主文件的运行中裸拷贝当一致备份。当前没有自动备份工具/恢复演练证明，不在用户真实库上试验。

商业上线前必须另行完成：

- 服务端认证、每次查询的租户授权、模型配置/附件/学习数据隔离；local_guard 不是认证，反向代理改 Host 也不是隔离。
- 事务边界与幂等请求（普通 retry 目前重复请求可产生多次 attempt；review 已有单 run 防重复）、版本化迁移、备份恢复验证。
- 明文密钥的服务端 secret 管理、日志/错误脱敏、上传/存储/请求速率与模型成本限额、外部模型数据条款。
- 有健康监测的单进程部署起步；多进程/多副本前替换进程内协调机制；TLS、反向代理 SSE 配置、运行用户和持久卷、停机升级和回滚方案。
- 发布流水线、依赖传递锁定与供应链扫描、负载/磁盘耗尽/故障注入、告警、备份责任人及恢复目标。
- 支付/订阅尚无实现：权限/计费事件/回调验签/幂等/退款均需单独设计；不能直接在当前 local 用户键上叠加收费入口。

这些是部署前置工作，不是本次已交付功能；不要直接把本机端口开放到公网。

工具配置参考：[TypeScript checkJs](https://www.typescriptlang.org/tsconfig/checkJs.html)、[Ruff rule 配置](https://docs.astral.sh/ruff/configuration/)。
