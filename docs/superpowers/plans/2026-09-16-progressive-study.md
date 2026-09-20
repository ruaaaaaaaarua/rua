# Progressive Study Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for isolated provider/frontend tasks and integration review. Preserve the existing uncommitted project rewrite; do not commit unrelated changes.

**Goal:** Deliver the first usable question early while remaining questions are solved in the background, with official DeepSeek vision and streamed explanations.

**Architecture:** A session-scoped background job shares one authoritative session object with short interactive operations. OCR emits validated questions; a bounded solver consumes the first question immediately and later questions in batches of at most three. Completed questions remain interactive. Ordinary chat streams text; hints are buffered and checked before display.

**Tech Stack:** Python 3.9 / FastAPI / asyncio / SQLite; React / Vite / Vitest; OpenAI-compatible HTTP SSE.

## Global Constraints

- Preserve real questions, learning records, prior dirty edits and original photos.
- Key stays in local SQLite configuration only; never print it or put it in source/docs.
- Vision: official https://api.deepseek.com, model deepseek-flash. Solve/chat stay on the configured GLM profiles.
- Display correctness only after a complete validated result. Keep answers/explanations hidden until requested.
- One active background job per session. Retrying skips confirmed results; failed items remain retryable.
- Do not auto-select later questions, move scroll position, or navigate on job completion.
- Background completion must not overwrite chat, help flags, titles, edits or personal evidence.
- Test with fake providers first; separately report real-provider smoke checks and any measured latency without promising unmeasured speedups.

## Task 1: Provider streaming and fast small batches

Files: app/providers.py, app/prompts.py, tests/test_progressive_providers.py.

- [x] Add failing MockTransport tests for GLM stream parameters, text chunks, usage-only SSE frames, truncated streams, and independent batch prompts.
- [x] Add `stream_chat(context, text, mode='direct')` yielding plain text, not JSON, using existing chat policies.
- [x] Extend `_stream` to allow a plain-text system instruction, GLM 5.3 reasoning_effort low (never disabled thinking), usage chunks, and safe failures. Keep vision NDJSON behavior.
- [x] Apply low-effort GLM parameters to ordinary solve/chat too; keep useful bounded output budgets. Retain existing validated solve_batch interface.
- [x] Run provider suites and report evidence. Do not touch live keys/config.

## Task 2: Session background pipeline and streamed HTTP

Files: app/jobs.py (new), app/main.py, app/service.py, tests/test_progressive.py (new).

- [x] Add event-gated tests proving the first recognized question solves before OCR finishes, complete items remain usable, and batch fallback affects only missing/invalid items.
- [x] Add `POST /api/sessions/{sid}/process` returning decorated session promptly and `processing: true`. `GET /api/sessions/{sid}` returns the same active session and progress. Job lifetime is independent of the HTTP connection.
- [x] Process first question immediately; subsequent pending questions are grouped in up to three, at most configured solve concurrency (default two), no diagnosis. Use independent snapshots, validate all answers, persist each result. Error only failed items and preserve successes.
- [x] Interactive operations use authoritative active session. Reject destructive/transcript/reference mutations while processing, allow reveal/hint/chat/retry for confirmed questions; keep a separate processing flag irrespective of chat status.
- [x] Add `POST /api/sessions/{sid}/messages-stream` with SSE `delta` ({text}), `done` ({session}), `error` ({message}); hints buffer through existing guard. Persist only completed assistant reply. Mark help before first content exposure, including interrupted streams.
- [x] Add tests for duplicate jobs, mutation guards, chat/background interleaving, retry, stream interruption, and safe errors. Run backend suite.

## Task 3: Progressive frontend

Files: web/src/api.js, web/src/App.jsx, web/src/Study.jsx, web/src/styles.css, web/src/api.test.js, web/src/Study.test.jsx.

- [x] Tests first for process API, SSE message events and truncation, and confirmed-question controls during background work.
- [x] Upload returns after `/process` starts; use background GET polling only while processing, scoped to session ID. Opening a session resumes pending work through idempotent process. Do not use global busy throughout processing.
- [x] API `process(id)` and `messageStream(id,body,onDelta)` with documented SSE events above. Render a temporary assistant message for the selected question/revision; finalize from server session, display interruption without inventing a complete answer.
- [x] Ordinary follow-up and requested expanded explanation stream; hints continue buffered. For explanation keep current concise saved analysis immediately available and offer expansion through selected-question chat.
- [x] Preserve answer hiding, photo correctness and optional retry. Disable pending-question actions, concurrent uploads/destructive edits for a processing session. Navigation remains possible while background processing.
- [x] Add quiet progress and ensure callbacks never replace another opened session. Run Vitest and production build.

## Task 4: Configuration, integration and review

- [x] Make SQLite backup with owner-only permissions before changing live profile settings.
- [x] Configure official DeepSeek vision using supplied key through non-echoing stdin, leave GLM solve/chat routing unchanged.
- [x] Run pytest, Vitest, build, inspect browser against a fake delayed provider. Verify first useful card and interaction while later work continues.
- [x] Run one small authorized real-provider connection/vision check if feasible; never log raw credentials or prompts. Record measured result separately from mock timings.
- [x] Independent code review, address important findings, rerun covering suites, safely restart local server only when idle.

## Progress

- Design approved by user on 2026-09-16. Initial inspection: prior solve_batch path unused; OCR 54.6 s in recent real run; individual solves mostly 12–28 s, one failed request 122 s; current global UI lock prevents interacting with partial results.
- All four tasks completed and reviewed. Final automated checks: 80 backend tests, 26 frontend tests, production build and Wiki validation passed. Detailed real-call results, caveats and browser checks: `2026-09-16-progressive-verification.md`.
- User explicitly requested a local Git archive after completion; preserve the current feature branch, with no remote push and no private data staged.
