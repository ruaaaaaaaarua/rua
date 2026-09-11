# Conversation Workspace and Analysis Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the chat workspace compact and resizable while preventing a failed batch diagnosis from re-solving every question sequentially.

**Architecture:** React owns a persisted, clamped conversation height and renders an accessible separator. FastAPI keeps model-routing configuration server-side. `LearningService` preserves batch solutions through diagnostic retry and uses per-profile concurrency only for the remaining fallback work; `ModelGateway` records sanitized failure kinds and scopes rate windows to an account identity.

**Tech Stack:** React 18, Vite/Vitest, FastAPI, Pydantic, asyncio, httpx, pytest.

## Global Constraints

- Do not expose or persist prompts, raw provider responses, or API keys in frontend payloads or call records.
- Keep `generate` and `verify` on their current GLM mapping unless the user changes those mappings explicitly.
- Preserve legacy global `parallel` settings; profile-level `parallel` takes precedence.
- Batch success remains the preferred two-call path; fallback must preserve solution/diagnosis confirmation rules.

---

### Task 1: Persisted, accessible conversation resize control

**Files:**
- Modify: `web/src/domain.js`
- Modify: `web/src/domain.test.js`
- Modify: `web/src/App.jsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Produces `clampConversationHeight(value, viewportHeight)` and `savedConversationHeight(storage, viewportHeight)` for `Conversation`.
- Produces a `Conversation` section with `style={{ '--conversation-height': '<px>' }}` and a keyboard/pointer separator.

- [ ] **Step 1: Write failing domain tests**

```js
expect(clampConversationHeight(20, 900)).toBe(156)
expect(clampConversationHeight(2000, 900)).toBe(660)
expect(savedConversationHeight({ getItem: () => '220' }, 900)).toBe(220)
```

- [ ] **Step 2: Run `npm test -- --run` in `web/` and verify the imports fail.**

- [ ] **Step 3: Implement the two helpers and use them in `Conversation`.**

```js
const resize = event => {
  const startY = event.clientY
  const startHeight = height
  const move = next => setHeight(clampConversationHeight(startHeight + startY - next.clientY, window.innerHeight))
  window.addEventListener('pointermove', move)
}
```

Render `role="separator"`, `aria-orientation="horizontal"`, pointer handlers, and ArrowUp/ArrowDown handlers. Store a finalized height under `grid-learning.conversation-height`.

- [ ] **Step 4: Set the CSS panel basis to `var(--conversation-height, 240px)` and make its message area scroll.**

```css
.conversation { flex: 0 0 var(--conversation-height, 240px); min-height: 156px; max-height: none; }
.conversation-resizer { height: 10px; cursor: row-resize; touch-action: none; }
```

- [ ] **Step 5: Re-run `npm test -- --run` and `npm run build` in `web/`; commit `feat: add resizable compact conversation panel`.**

### Task 2: Retain batch solutions through diagnosis failure

**Files:**
- Modify: `tests/test_evidence_boundaries.py`
- Modify: `app/service.py`

**Interfaces:**
- `LearningService.analyze` retries `diagnose_batch` exactly once on `ProviderError`.
- Fallback receives `solution` when a batch solution exists and calls only `gateway.diagnose` for that question.

- [ ] **Step 1: Write a failing test with two batch solutions and a `diagnose_batch` that raises twice.**

```python
assert gateway.batch_diagnoses == 2
assert gateway.single_solves == 0
assert gateway.single_diagnoses == 2
assert all(q['analysis']['status'] == 'confirmed' for q in result['questions'])
```

- [ ] **Step 2: Run the focused pytest case and verify it fails because `analyze` re-solves questions.**

- [ ] **Step 3: Implement a two-attempt batch-diagnosis helper and pass optional batch solutions into the fallback coroutine.**

```python
solution = solutions.get(index)
if solution is None:
    solution = await gateway.solve(question)
diagnosis = await gateway.diagnose(contextual_question, solution, self.related(question))
```

- [ ] **Step 4: Re-run the focused case and the full backend suite; commit `fix: reuse batch solutions after diagnosis failure`.**

### Task 3: Safe failure kinds and profile-level concurrency

**Files:**
- Modify: `tests/test_providers.py`
- Modify: `tests/test_evidence_boundaries.py`
- Modify: `app/providers.py`
- Modify: `app/store.py`
- Modify: `app/main.py`
- Modify: `app/service.py`
- Modify: `web/src/App.jsx`

**Interfaces:**
- `ProviderError(message, error_kind='provider_error')` carries only a safe category.
- `ModelGateway.parallel_for(task)` returns the selected profile value, then legacy global value, then 1.
- `Store.record_call` accepts `error_kind`; public APIs still omit credentials.

- [ ] **Step 1: Write failing tests for a schema failure record, profile precedence, and isolated rate-window keys.**

```python
assert event['error_kind'] == 'response_schema'
assert gateway.parallel_for('solve') == 3
assert gateway_a.rate_key(profile_a) != gateway_b.rate_key(profile_b)
```

- [ ] **Step 2: Run the focused pytest cases and verify the expected missing-interface failures.**

- [ ] **Step 3: Add safe error categories, use a SHA-256 derived rate key, and take `parallel` from the selected task profile.**

```python
identity = '\\0'.join((profile['base_url'], profile['model'], profile['api_key']))
return hashlib.sha256(identity.encode()).hexdigest()
```

- [ ] **Step 4: Add a profile “并发上限” number input (1–8) and Pydantic validation. Keep task selectors unchanged so `chat` can select a user-configured DeepSeek profile.**

- [ ] **Step 5: Run focused tests, full `pytest -q`, frontend tests, and production build; commit `feat: add per-profile model concurrency controls`.**

### Task 4: Controlled GLM and DeepSeek concurrency measurement

**Files:**
- Create: `docs/benchmarks/2026-09-11-provider-concurrency.md`

**Interfaces:**
- Records provider/model, tested concurrency, sample count, wall time, per-request time range, 429 count, and success count without a key or prompt transcript.

- [ ] **Step 1: Verify GLM and DeepSeek are configured locally; do not print configuration or keys.**
- [ ] **Step 2: Send the same minimal structured chat request with concurrency 1, 2, 3, and 4, stopping a provider after its first 429 or non-success response.**
- [ ] **Step 3: Write only aggregate results into the benchmark file and select a candidate profile value according to the global constraint.**
- [ ] **Step 4: Re-run full tests/build after applying selected local settings; commit `docs: record provider concurrency measurements`.**
