# Personal learning acceptance record

## Scope

Local current-branch upgrade, no public deployment. Core teaching content remains unfilled by design. All browser mutations use a disposable database and a fake model in `/tmp/personal-learning-qa.VIJIIh`; production sessions, images, credentials and answers are not used as fixtures.

## Backend checkpoint

- Implementation: `dec6f93`, followed by concurrency/date/evidence fixes `8937378`; report checkpoint `03dbee2`.
- Implementer reported: 16 focused tests, 96 full backend tests, knowledge validation (6 chapters / 18 nodes / 0 published cards).
- Independent task review: approved after fixes `457e3de..469f6dd`. Stale history, dependent assistant replies, per-message audit and demo exclusion verified from code. Implementer focused fix run: 16 passed in 1.57s.
- Controller fresh verification on `469f6dd`: `.venv/bin/python -m pytest -q` → 96 passed in 10.59s; `.venv/bin/python -m app.validate_knowledge` and `git diff --check` passed.
- Controller isolated API smoke passed: linked full published card content; unlinked detail 404; no internal file path/unlinked relations; review hint excludes answer/explanation and marks assisted; submitting leaves sibling events unchanged; profile round-trip; organization classifies one pending original without changing the four-original total. All records were temporary fixtures with a fake gateway.
- Repository privacy check: `git ls-files` shows no tracked `data/`, SQLite/database or uploaded image files; filename-only key-pattern scan of application/tests/docs/README returned no matches. Repeat at final checkpoint.

## Integration checks

Browser observations on the isolated fixture (Sep 17): paper/blueprint archive styles render; nickname/signature/theme/two chosen medals persist after reload; stats default off and toggle on; long CJK/Latin signature overflow was found and corrected (observed text right edge 313px inside 390px viewport). Review keeps selected B through hint, hides reference answer until submission, records assisted success, keeps completed run until explicit next, retains budget 3 on refresh, and all four originals remain with only selected original rescheduled. No production data was edited. A local SVG download event did not arrive in IAB; this is not yet a confirmed browser download success.

Sep 18 controller rerun at `6418390`: 44 frontend tests pass; production build succeeds with the existing >500 kB JavaScript chunk warning. Final whole-change review identified public candidate metadata and reveal→hint response leaks; fixes underway. Browser-tool inventory and tab reconnection timed out on resumption, so additional browser checks remain unverified rather than assumed successful.

Acceptance checklist (API/unit evidence supplements, but does not replace, uncompleted browser checks):

- Personal Wiki: only linked node is listed; published linked body readable; unlinked published detail returns 404; empty/draft states remain useful.
- Review: 3/5/10 budget, representative plus all originals, explicit organization feedback, correction, preserved selections, assisted hints, unchanged siblings.
- Personal context: revealed-only historical cards, correct session/question navigation, source deletion/revision invalidation.
- Archive: paper and blueprint styles, earned/locked medals, editable display fields, save/reload and save-failure behavior.
- Share: selected earned medals only, counts opt-in, escaped local SVG, preview/download consistency, no external transmission.
- Responsive/reduced-motion styles and no theme leakage into study workspace.

## Final verification — 2026-09-19

- Final response-boundary fixes: public sessions omit internal `candidates`; both cached and newly generated review hints use a whitelist, including after revealing an answer. Original evidence and stored question data are unchanged.
- Two new backend regressions were also run against an isolated archive of `6418390`: both failed for the expected leaked fields. They pass with the fixes. No user data or real model was used.
- Independent reviewer `boundary_review` examined the four final implementation/unit-test files and their callers: no blocking findings; 18 personal-backend tests and 12 archive tests passed independently.
- Full root `npm run check` passed: Python/JavaScript type checks, correctness lint, knowledge validation, 116 backend tests (1 explicitly opt-in private HEIC test skipped), 45 frontend tests, production build, 3 Chromium browser tests. Existing large JavaScript chunk warning remains; no check was weakened.
- New browser regression confirms a real SVG download succeeds, its parsed contents match the visible preview, and special characters are escaped. This resolves the earlier IAB-only download uncertainty for Chromium, not a claim of IAB compatibility.
- Desktop (1440px) and mobile (390px) archive screenshots are generated under ignored `web/test-results/`; reviewer visually inspected readable cards and controls. Earlier paper/blueprint and review interaction observations remain applicable.
- This is still a local single-user framework: no authentication, tenant isolation, remote MCP hosting, or real-model accuracy benchmark. Knowledge remains 6 chapters / 18 nodes / 0 published teaching cards.
- The running real-data backend on port 8765 was not restarted in this final verification. Restart the local service to load backend changes; this record does not claim an in-place data upgrade or production release.
- Separate uncommitted engineering-baseline tooling and mixed-owner README edits are intentionally left outside this task's commits. The full gate above used that tooling in the current workspace; it is not a claim that those separate files are committed.

## Handoff gates

- Fresh backend tests, frontend tests, production build, knowledge validation, whitespace check.
- Independent whole-change review and fixes.
- Before restarting against real data: stop writes and back up the complete data directory; follow the development rollback instructions. Real-data restart is not part of this verification.
- Local Git checkpoint, no credentials/data/artifacts from private production sessions committed; no push.

Rollback: revert the relevant feature/fix commit(s) rather than resetting the shared branch; rebuild the UI and restart locally. Code rollback is not data restoration. No data migration was introduced in this final fix wave.
