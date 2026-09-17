# Personal learning backend report

## Delivered contracts

- Optional solve-time classification is schema-tolerant: malformed metadata becomes `null` while a valid answer remains usable. Grouping requires a known linked knowledge set, controlled method/variant, confidence `>=0.8` (or an explicit manual correction), and exact normalized `target:` / `method:` / `boundary:` conditions. Confidence is only an uncalibrated model estimate, not correctness evidence.
- Manual classification is authoritative, validates known knowledge IDs, updates automatic links, survives solving the same revision, and is invalidated by question edits or incompatible manual relinking. Existing classification can be organized in at most 12-question requests with bounded concurrency and stale-revision checks.
- Review queue keeps the old `items/due_count/total` shape and adds conservative `groups`, interleaved `recommended`, and `limit`. True duplicate originals consume one recommendation slot, while the full originals/history remain. Same stem with different options is not a duplicate. A representative never mutates siblings.
- Progression uses independent original-review successes on distinct Asia/Shanghai dates. Later failure or assisted work steps back to the easiest available member; uploads and source observations cannot prove cross-day progression.
- Review hints are cached per run, mark all simultaneous runs assisted before returning, and never return answer/explanation fields or receive historical solutions.
- Public Wiki/knowledge projections contain only nodes linked to extant personal questions. Published linked cards may expose their full teaching content; drafts are explicitly unfilled. Internal solving can still retrieve any relevant published core node. Catalog file names and unlinked relation targets are not public.
- Follow-up retrieval is capped at two extant, current-revision, confirmed related questions. It is omitted from solves, hints, and unrevealed-question follow-ups. Public history is sanitized; internal audit stores only core IDs/versions, history IDs/revisions, and provider profile/model identity (never credentials).
- Archive preferences live in a separate SQLite table. Three medals are recomputed from current valid evidence, revisions, core versions, independent review facts, and Asia/Shanghai dates; theme never changes eligibility.

## API examples for frontend

### Classification taxonomy and correction

`GET /api/review-taxonomy`

```json
{
  "methods": [{"id":"concept","label":"概念辨析"}],
  "variants": [{"id":"direct","label":"直接应用"}],
  "difficulties": [{"id":"basic","label":"基础"}],
  "condition_requirements": ["target:","method:","boundary:"]
}
```

`PATCH /api/sessions/{sid}/questions/{qid}/classification`

```json
{
  "knowledge_ids":["psa-per-unit"],
  "primary_knowledge_id":"psa-per-unit",
  "method":"calculation",
  "variant":"direct",
  "conditions":["target:base conversion","method:ratio conversion","boundary:shared base power"],
  "difficulty":"basic",
  "confidence":1.0,
  "reason":"人工确认的题目要求"
}
```

The response is the decorated public session. Unknown IDs or incomplete controlled conditions return `422`.

### Historical organization

`POST /api/reviews/organize` accepts `{}` or an optional bounded scope:

```json
{"question_ids":["q1","q2"]}
```

Response:

```json
{"classified":2,"remaining":4,"failed":0}
```

At most 12 currently confirmed, unclassified questions are attempted. Provider/metadata failures increment `failed` without fabricated writes. Active background solving or another organization request returns `409`; edits made while the model is running fail the stale write.

### Review queue and hint

`GET /api/reviews?limit=5` (`limit` is `3`, `5`, or `10`):

```json
{
  "items":[{"session_id":"s1","question_id":"q1","text":"...","number":1,"knowledge":[{"id":"psa-per-unit","name":"标幺值"}],"state":"近期答错","due":true,"due_at":"...","classification":{},"group_id":"...","difficulty":"basic","reason":"..."}],
  "due_count":1,
  "total":1,
  "groups":[{"id":"...","knowledge_id":"psa-per-unit","knowledge_name":"标幺值","method":"calculation","method_label":"计算求解","difficulty":"basic","difficulty_label":"基础","items":[],"representative":{},"reason":"..."}],
  "recommended":[],
  "limit":5
}
```

`POST /api/reviews/{rid}/hint`:

```json
{"id":"rid","status":"ready","help_kind":"assisted","hint":"先检查基准量是否一致。","question":{}}
```

No `answer` or `explanation` is present.

### Personal Wiki

- `GET /api/wiki?q=...`: linked summaries only; no `content_file`, raw relations, or unlinked nodes.
- `GET /api/wiki/{kid}`: `404` unless linked; published content is included, draft `content` is `""` and `has_content=false`; related nodes are filtered to linked IDs.
- `GET /api/knowledge`: linked node summaries only.
- `GET /api/framework`: general chapter skeleton only.

### Archive

`GET /api/archive`:

```json
{
  "profile":{"nickname":"学习者","signature":"","theme":"paper","selected_medals":[],"show_stats":false},
  "stats":{"questions":3,"linked_nodes":2,"review_days":1},
  "medals":[{"id":"first_connection","title":"第一次连接","description":"...","earned":true,"earned_at":"2026-09-17","evidence":[{"session_id":"s1","question_id":"q1","revision":1,"date":"2026-09-17"}]}]
}
```

`PUT /api/archive`:

```json
{"nickname":"Grid","signature":"稳稳地学","theme":"blueprint","selected_medals":["first_connection"],"show_stats":false}
```

Nickname/signature limits are 30/100 characters; selected medals are unique, at most three, known, and currently earned.

## Files changed

- New: `app/classification.py`, `app/personal.py`, `app/archive.py`, `tests/test_personal_backend.py`.
- Updated: `app/models.py`, `app/prompts.py`, `app/providers.py`, `app/service.py`, `app/study.py`, `app/main.py`, `tests/test_api.py`, `tests/test_evidence_boundaries.py`.

## TDD and verification evidence

Initial RED:

```text
.venv/bin/python -m pytest -q tests/test_personal_backend.py
8 failed in 0.69s
```

Focused GREEN after implementation and added boundary cases:

```text
.venv/bin/python -m pytest -q tests/test_personal_backend.py
16 passed
```

Full backend regression and knowledge validation:

```text
.venv/bin/python -m pytest -q
96 passed in 9.75s

.venv/bin/python -m app.validate_knowledge
电力系统分析：6 个章节，18 个节点，0 篇已发布正文。校验通过。
```

`git diff --check` also completed with no whitespace errors.

## Limitations

- No live provider call was made. Classification quality and confidence thresholds are controlled-contract behavior tested with deterministic fakes; model estimates are not calibrated and real-model grouping quality still requires observation.
- Organization reuses the existing structured solve response to obtain classification, so it also asks the provider to solve the selected originals; only validated classification is committed.
- This remains a local single-user privacy boundary, not a multi-tenant authorization system.

## Commit

Recorded after final verification; see commit listed in the task handoff.
