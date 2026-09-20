# Study interaction improvements

**Goal:** 落实用户已确认的每日命名、HEIC 输入、逐题进度、直接核对和可选提示、按题讨论。

**Architecture:** 延用本地 FastAPI/SQLite 与 React；每日计数由数据库事务分配；图片在本机标准化；解题有限并发、客户端读取已保存进度；提示复用按题聊天并记录帮助事实。

**Tech Stack:** Python 3.9、SQLite、macOS sips、React、Vitest。

## 已确认约束

- 核对完成直接显示照片答案与对错；不自动展开完整解析，不强迫再次提交。
- 提示是按需的一条短引导，不是强制分级教学；不保证语义上绝不泄题。判断题对错本身可泄露答案。
- 原作答不覆盖，提示后的新提交是辅助作答；未作答仍可直接看解析。
- 新会话标题为电力系统分析N · YYMMDD，按北京时间每天重置；不覆盖已有自定义标题。
- 同一学习会话内按题隔离讨论；旧无题目标签的历史只在公共讨论展示。
- 不调用用户付费模型作测试，不删除旧学习记录或改模型密钥。

## Tasks

- [x] 1. tests/test_interactions.py：编写日期重置/删除不复用、提示来源与帮助、按题隔离、并发默认值测试；运行 pytest 观察失败。
- [x] 2. app/store.py：事务计数器创建名称；app/service.py/prompts.py/main.py：独立 hint 端点与线程标签/修订号，隔离参考资料，客户端错误保留；验证测试。
- [x] 3. app/images.py/main.py：HEIC 本机转 JPEG，超大普通图片标准化；具体格式/体积/数量错误；测试真实 HEIC 与失败数据不修改原文件。
- [x] 4. app/providers.py：默认解题并发 2，保留显式限制；web/src/api.js 增加轮询进度的 analyze 方法，不自动重新发起模型请求。
- [x] 5. web/src/Study.jsx/App.jsx/domain.js：照片已作答显示判定与静态选项，提示与解析入口，主动重答；按题聊天显示；每日命名与改名；上传支持 HEIC。先用 SSR/Vitest 检查不泄露完整解析与无需提交。
- [x] 6. 完整 pytest/Vitest/build、真实文件本地转换、浏览器或 SSR 联调；备份数据库、重启本地服务并更新 README。

## Verification commands

```sh
.venv/bin/python -m pytest tests/test_interactions.py -q
npm --prefix web test
.venv/bin/python -m pytest -q
npm --prefix web run build
git diff --check
```

执行方式：用户已要求立即修改，本会话内按任务执行，不另开审批轮次；不自动提交此前未提交的用户工作区变更。

## 验证结果（2026-09-16）

- 完整后端 60 项通过；前端 15 项通过；生产构建成功（仍有原先的大包体积提示）。
- 浏览器使用真实 IMG_1430.HEIC + 临时数据库 + 模拟模型：上传转 JPG、直接判定、隐藏解析、提示缓存与本题聊天、自愿重答并标记辅助均通过；浏览器无 error/warn。
- 独立审阅发现修改题目会抹去近期帮助暴露，已先复现失败测试，再修正为保留帮助时间事实；对错判断仍按修订撤销。
- 未使用付费模型测试；未验证真实学科提示质量或承诺提速倍数。
