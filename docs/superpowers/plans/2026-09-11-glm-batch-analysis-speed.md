# GLM Batch Analysis Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GLM batch solve and diagnosis requests smaller and faster while retaining validated per-question fallback.

**Architecture:** Add a batch-only request policy to `ModelGateway._call`, then make batch prompts and service diagnosis context conform to it. Non-batch requests keep the existing configured thinking and token behavior.

**Tech Stack:** Python 3.9, FastAPI service layer, httpx, Pydantic, pytest.

## Global Constraints

- Only `solve_batch` and `diagnose_batch` use the 4,096 completion-token policy; GLM 5.3 uses `reasoning_effort: low`, while compatible models disable thinking.
- Do not alter Kimi streaming extraction or ordinary/individual GLM request policy.
- Preserve existing batch validation and per-question fallback.

---

### Task 1: Add and verify the batch request policy

**Files:**
- Modify: `app/providers.py:139-167,276-311`
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces: `_call(task, content, schema, coerce=None, batch=False)` where `batch=True` applies the fixed batch policy.

- [ ] **Step 1: Write failing tests**

```python
assert solve_body["reasoning_effort"] == "low"
assert solve_body["max_tokens"] == 4096
assert diagnose_body["reasoning_effort"] == "low"
assert diagnose_body["max_tokens"] == 4096
```

- [ ] **Step 2: Run the provider tests and verify the assertions fail because batch calls still inherit default policy.**

Run: `.venv/bin/python -m pytest tests/test_providers.py -q`

- [ ] **Step 3: Implement the optional `batch` policy and pass `batch=True` only from `solve_batch` and `diagnose_batch`.**

```python
if batch:
    body["max_tokens"] = 4096
    body["reasoning_effort"] = "low"
```

- [ ] **Step 4: Re-run the provider tests and verify they pass.**

### Task 2: Shrink prompt and diagnosis context

**Files:**
- Modify: `app/prompts.py:solve_batch_prompt,diagnosis_batch_prompt`
- Modify: `app/service.py:diag_input`
- Test: `tests/test_providers.py`, `tests/test_evidence_boundaries.py`

**Interfaces:**
- Consumes: `LearningService.related(question)`.
- Produces: diagnosis batch items whose `history` list contains at most three rows.

- [ ] **Step 1: Write failing tests**

```python
assert "一至两句" in solve_batch_prompt([])
assert "explanation" not in diagnosis_batch_prompt([])
assert all(len(item["history"]) <= 3 for item in gateway.diagnose_items)
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing concise prompt/context policy.**

Run: `.venv/bin/python -m pytest tests/test_providers.py tests/test_evidence_boundaries.py -q`

- [ ] **Step 3: Require short solve explanations, remove the diagnostic explanation request, and pass `self.related(q)[:3]`.**

- [ ] **Step 4: Re-run focused tests and verify they pass.**

### Task 3: Regression and live performance verification

**Files:**
- Test: `tests/`

- [ ] **Step 1: Run full backend tests.**

Run: `.venv/bin/python -m pytest -q`

- [ ] **Step 2: Run front-end tests and production build.**

Run: `npm test -- --run src/domain.test.js` and `npm run build` from `web/`.

- [ ] **Step 3: Restart the local service and analyze an isolated copy of the same ten-question image. Record batch solve time, batch diagnosis time, total analysis time, and completed-question count.**

- [ ] **Step 4: Commit only design documentation when source files overlap existing user changes; do not create a mixed source commit.**
