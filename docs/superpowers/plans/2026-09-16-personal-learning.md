# Personal Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Read the task brief first, implement tests before code and report evidence. User explicitly requested implementation; no further design approval pause.

**Goal:** Deliver personal-context teaching, grouped adaptive original-question reviews, and a themed archive/medal/share experience.

**Architecture:** Preserve FastAPI + SQLite session workflow. Add focused modules for question taxonomy, review projections/personal history and archive; shared UI consumes explicit data endpoints. New model metadata accompanies the existing solve call; old questions can be classified explicitly in small batches.

**Tech Stack:** Python 3.9, FastAPI/Pydantic, SQLite, React 19/Vite/Vitest; existing dependencies only.

## Global Constraints

- No core knowledge content authoring, generated questions, public community, payments or cloud deployment.
- Core content is authoritative reference material; personal history is experience, not answer authority.
- No inferred psychological error causes, mastery percentages or fabricated sources.
- All existing records preserved; classification groups never delete originals or mark siblings passed.
- Hidden-answer/hint mode excludes historical answers/explanations; incomplete and pending warnings remain.
- Personal Wiki only exposes linked nodes and their full published teaching cards; draft content is not fabricated.
- Local single-user mode remains local; no claim of production multi-tenant protection.
- Archive themes do not change the study workspace or achievement eligibility.
- No API keys, user database, photographs or backups in Git. No push.

## Task 1: Backend learning contracts

Read `docs/superpowers/plans/2026-09-16-learning-backend-brief.md` for complete behavior/API requirements. Own `app/` and `tests/` plus backend report. Preserve safe concurrency around active StudyJobs. Add focused modules rather than bloating service.py.

- [ ] RED: classification defaults, conservative grouping, difficulty progression, independent solve/no history, bounded relevant history in chat, hint history redaction, deleted/revised exclusion, scoped Wiki, archive eligibility and preference validation, review hint safety.
- [ ] GREEN: implement interfaces from brief, safe schema parsing, prompt modifications and routes.
- [ ] Run `.venv/bin/python -m pytest -q` and `.venv/bin/python -m app.validate_knowledge`.
- [ ] Document actual JSON responses and TDD outputs in backend report; commit only owned files.
- [ ] Independent task review; fix substantive findings with regression tests.

## Task 2: Frontend learning and archive

Read `docs/superpowers/plans/2026-09-16-learning-frontend-brief.md` and Task 1 API report. Own `web/` and frontend report. No backend edits without controller agreement.

- [ ] RED: grouped representative view, all-originals path, correction form payloads, hidden history/provenance behavior, safe scoped themes and share export escaping, preference saving and earned-only selections.
- [ ] GREEN: implement review UI, personal knowledge empty/link view, optional provenance, archive/medal/share UI.
- [ ] Run `npm --prefix web test` and `npm --prefix web run build`.
- [ ] Commit owned files and detailed test/report evidence.
- [ ] Independent task review; fix substantive findings.

## Task 3: Integration and handoff

- [ ] Run all backend/frontend tests, build, knowledge validation and Git whitespace check.
- [ ] Back up local SQLite safely, restart only this application's server after checking no active jobs.
- [ ] Browser verification: linked-only Wiki, grouped review and all originals, classify/correct, hidden-answer history, archive themes and share preview; use disposable test records outside user database.
- [ ] Whole-change review against baseline `d2094ef`; address findings.
- [ ] Update README, record verification evidence and local Git archive. No push.
