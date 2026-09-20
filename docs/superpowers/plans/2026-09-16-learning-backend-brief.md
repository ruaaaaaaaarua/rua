# Task 1 — Backend requirements

Read the approved spec `docs/superpowers/specs/2026-09-16-personal-learning.md`. Implement in app/ and tests/ only; write report here: `docs/superpowers/plans/2026-09-16-learning-backend-report.md`. Use TDD, focused tests while iterating and full backend suite before commit. Baseline is d2094ef (80 tests). Preserve user data; no live provider calls required. Existing models support only choice/judge, no essays required.

## Organization and API contract

Create focused modules `app/classification.py`, `app/personal.py`, `app/archive.py` as appropriate; integrate with existing LearningService/StudyRecords/StudyJobs rather than replacing them. Backend owns all app files. Current local API is single-user, no public deployment.

### Classification

Add optional `classification` to Solution/BatchedSolution. Invalid/missing classification metadata must safely become unclassified without invalidating otherwise valid solution output. Use controlled method codes and variants, validated known knowledge IDs, basic/intermediate/advanced difficulty, estimated confidence, reason and distinguishing conditions. Keep keys deterministic; conservative group requires high confidence (>=0.8), nonempty conditions and exact normalized method/variant/conditions/all-linked-knowledge-ID match; otherwise singleton. Do not group just by knowledge label. Manual correction is authoritative and survives re-solving same revision; invalidate on text/option edit or incompatible relinking. Use optional metadata in solve prompt plus server-controlled catalog/taxonomy input, no added model call for new solves. Classify question demands without user answers or personal evidence.

Provide `PATCH /api/sessions/{sid}/questions/{qid}/classification` with validated classification object, return decorated session. A manual classification may mark grouping as confirmed without AI confidence. Unknown knowledge IDs rejected. Do not mutate core knowledge content. Provide taxonomy labels via `GET /api/review-taxonomy` (generic methods/difficulties/variants, no hidden core catalog).

`POST /api/reviews/organize` explicitly classifies at most 12 existing unclassified confirmed questions via bounded batches; returns counts `{classified, remaining, failed}`. Guard against active session jobs/concurrent edits and stale revision writes. Report model failure safely, don't convert failure into fabricated metadata. Can accept supported scoped IDs if needed. Document exact shape in report.

### Review queue

Keep GET `/api/reviews` backward compatible `{items,due_count,total}`; add `groups`, `recommended`, `limit` with query limit 3/5/10 default5. Group contains id, knowledge_id/name, method/difficulty labels, items, representative (queue item), reason. Item contains session_id/question_id, text/number/knowledge/state/due/due_at plus classification/group_id/difficulty/reason. Unclassified grouped only as singleton. Deduplicate identical original content for recommendations only; preserve all items/history. No sibling event/date mutation when representative passes. Pick one per group and interleave knowledge domains. Prefer error/assisted and due items, progressive difficulty when comparable method+conditions exist. Do not silently reschedule backlog. For learned method independent cross-day successes prefer next difficulty; failures/help select basic, skip incomplete/pending/legacy/stale source. New uploaded observations may affect priority but cannot prove independent mastery. Independent cross-day interval accounting must use Asia/Shanghai, retain recent-help exposure guard.

Add POST `/api/reviews/{rid}/hint`, returns review run plus `hint` and `help_kind=assisted`, never `answer` or `explanation`. Call gateway chat with hint-only policy and no historical solutions. Cache per run; mark all simultaneous relevant runs helped before output. Preserve existing reveal/answer APIs. Never use unsupported free-text grading.

### Personal retrieval and core privacy

Expose only knowledge IDs currently linked to extant user's questions via `/api/wiki`, `/api/wiki/{kid}`, `/api/knowledge`; detail full published content is allowed, draft body hidden/unfilled; unlinked detail=404 and filter related/candidates metadata. Preserve internal library search unrestricted for solving, including prerequisites when relevant. Do not publicly send catalog content_file/internal metadata. Manual linking UI can choose existing personal nodes/candidates without seeing whole library; AI uses server catalog.

Add bounded personal history retrieval independent of core publication: max2 extant confirmed other questions, excluding current question, same relevant knowledge plus preferably compatible method. Include IDs/revisions/dates/earlier errors/latest improvement; never infer psychological error cause. Solving request must not contain personal history. Ordinary followup may receive history; hint-only OR not-revealed current question receives no historical answer/explanation (safest omit personal history). Save audit in server session/question/message: core IDs/versions, historical source IDs/revisions and provider model/profile identity, no credentials and no full core chunks. `public_session` strips internal audit. Frontend gets optional `related_history` only for revealed explanation, sanitized titles/states/source links, max2. Recompute public references to exclude deleted/revised sources; stale saved chat history should not resurrect removed personal references.

Prompt KNOWLEDGE_POLICY no longer asks model to announce wiki-empty/model-supplement or separate source sections. Keep missing conditions, uncertainty and conflicts explicit. Plain-language explanations based on reference content. Optional citations are consulted references, not certified attribution. Preserve audit without exposing it by default.

### Archive and preferences

GET `/api/archive` returns `{profile:{nickname,signature,theme,selected_medals,show_stats},stats:{questions,linked_nodes,review_days},medals:[{id,title,description,earned,earned_at,evidence:[{session_id,question_id,revision,date}]}]}`.
PUT `/api/archive` validates profile prefs nickname<=30,signature<=100, theme enum paper/blueprint, selected_medals max3 IDs unique and earned only, show_stats bool defaultfalse. Persist separate SQLite table, never within provider settings. Stable default nickname='学习者', signature='', theme='paper', selected_medals=[]; default share omits stats.
Three evidence-backed medals: first_connection (extant linked confirmed question); next_day (independent original review on later Asia/Shanghai day than source observation); reconnected (valid wrong observation then independent correct review on later local day). Eligibility from valid current-revision events/current confirmed source; reject deleted/edited/disputed evidence; revisions/core-version mismatches treated conservatively. No mastery claims. Recompute on GET, filter saved selections when eligibility vanishes, do not fabricate events. Same facts yield same medals regardless theme. No public share endpoint needed; frontend generates local card.

## Required tests

Assert valid answer survives malformed metadata; hidden knowledge cannot enumerate/detail but internal solve can retrieve; drafts never expose body; unknown/link corrections validated. Assert same-topic/different-conditions not grouped, duplicates don't multiply recommendation credit, selected representative does not pass siblings, basis difficulty progression, pending excluded, budget respected, Shanghai midnight not UTC. Assert core-empty personal-history works, latest success accompanies old wrong, unrevealed/hint prompts contain no old answers, solved prompts contain no personal history, deletion/revision excludes stale references. Assert profile validation/no keys/earned-only medals/source invalidation. Assert hints have no answer fields and mark help; organizing failure no stale writes. Update legacy expectations only for intentionally changed product semantics; no weakened boundary tests.

Report exact API examples to frontend, files changed, RED/GREEN commands/output, full suite, commits and limitations.
