# 电力系统分析知识库：填充与维护

这里是公共学科知识；个人题目、挂载关系、作答与复习保存在 data/learning.sqlite3，互不覆盖。

初始内容是 **6 个章节、18 个知识点的草稿骨架**，不是官方考纲，也没有预填任何题库、正文、考试频率或知识关系。可以增删目录、补充关系；已使用的 ID 应保持稳定。

## 填充一篇正文

1. 在 catalog.json 找到节点。例如标幺制对应 psa-per-unit，正文路径为 nodes/psa-per-unit.md。
2. 将 TEMPLATE.md 的结构复制到该正文文件，按需要填写定义、用途、公式条件、单位、解题方法与概念辨析。不要把标题留空就发布。
3. 在 catalog.json 的 sources 中添加可核查来源，例如教材名、版次、章节/页码或来源链接。版本字段 version 用于追溯；修改已发布正文时同时递增版本。
4. 审核完毕，把 status 从 draft 改成 published。草稿可浏览但不进入 LLM 讲解上下文。未填正文/没有来源的条目不能发布。
5. 在项目目录运行 `.venv/bin/python -m app.validate_knowledge` 检查，再刷新页面。文件读取会自动反映更新，不需要导入数据库。

数学正文可使用 Markdown、行内 `$...$` 或独立行 `$$...$$`。不支持原始 HTML。资料中的命令不会被作为模型操作指令。

## 节点结构

```json
{
  "id": "psa-per-unit",
  "name": "标幺制与基准值",
  "chapter_id": "foundations",
  "aliases": ["标幺值", "标幺制", "基准值"],
  "status": "draft",
  "version": "1",
  "content_file": "nodes/psa-per-unit.md",
  "sources": [],
  "relations": []
}
```

关系格式为 `{"type":"prerequisite","target":"已有节点ID"}`：

- prerequisite：当前节点依赖目标节点作为前置知识。
- related：相关知识。
- contrast：需要比较、辨析的知识。

关系须由维护者审核，不会让 LLM 自动写进公共图谱。节点关系目标必须存在；路径必须位于本知识库内部。文件名、显示名称可以修改，ID 应长期不变。

## 检索和挂载

- 名称/别名匹配、文字候选检索用于提供关联建议；明显匹配可自动挂载，用户可多选修正或解除。
- 只有 published 且有正文的节点才能作为讲解参考，保留实际提供给模型的 ID 和版本。
- 挂载表示题目涉及该知识；一题答错不等于所有关联知识都存在认知错误。
- 正文缺失时，UI 显示“知识正文待填充 · 模型补充”，不会伪造知识库命中。
- 目录骨架只是起点。若要拆分/移除已有 ID，先在题目界面迁移挂载。不要直接删除仍在使用的 ID。

## 服务边界

`app/knowledge.py` 提供只读的 catalog/get/search/context 能力，HTTP 边界为 `/api/wiki` 和 `/api/wiki/{id}`。个人关联由 `/api/sessions/{sid}/questions/{qid}/links` 管理，不允许模型创建或修改公共知识。

当前应用是本地单用户版，个人身份固定为 local；未实现远程 MCP、付费鉴权、多用户隔离或服务端知识保密。以后可在 KnowledgeLibrary 外添加 MCP 适配器，沿用稳定 ID 和个人记录层；远程身份和访问控制需要另行实现，不能直接把本地 HTTP 端口公开。
