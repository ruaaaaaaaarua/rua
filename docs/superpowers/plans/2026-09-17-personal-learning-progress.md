# Personal learning implementation ledger

- Baseline: d2094ef. Approved implementation plan/spec: 5532686.
- User confirmed continuing in current branch `codex/power-study-workspace`.
- Baseline verified: 80 backend tests, 26 frontend tests pass.
- 2026-09-16 backend worker stopped by model usage limit after creating `tests/test_personal_backend.py`; no implementation commit was made.
- 2026-09-17 resumed backend Task 1 from the existing test file. Do not rerun earlier progressive-solving tasks.
- Task 1: complete (`5532686..469f6dd`, independent task review clean after `457e3de` stale-history/per-message-audit/demo fixes). Reviewer confirms transitive dependent-message invalidation and public audit redaction. No open findings.
- Task 2: complete (`469f6dd..6418390`, independent task review clean after budget/citation/archive recovery fixes). 44 frontend tests passed on controller rerun; build succeeds with existing large-chunk warning.
- Task 3: implementation and local verification complete on Sep 19. Final response-boundary defects (unlinked candidates and hint-after-reveal answer fields) fixed and independently reviewed without blockers. Two regressions fail as expected against isolated HEAD 6418390 and pass after the fix. Root `npm run check` passes (116 backend / 45 frontend / 3 Chromium browser tests; 1 opt-in HEIC skip). Real SVG download and preview equality verified in Chromium; IAB download remains unverified. Desktop/mobile screenshots inspected. See acceptance record for exact coverage and remaining local-service restart boundary.

## Acceptance checks for browser fixture

Use an isolated database without real model credentials. Fixture must include: two same-method basic/advanced questions, a different-condition question, one unclassified question, a wrong-then-cross-day-correct record, a published linked card and a hidden published card. No fixture records enter the user's database.

1. Personal Wiki lists only mounted nodes; linked published card shows full content; hidden card returns 404 through API.
2. Review opens with representative groups and bounded selection; all originals remain available.
3. Manual correction updates classification/grouping without deleting an original.
4. Review hint leaves answer hidden, shows assisted state, and submitting affects only selected original.
5. Revealed question offers historical counterpart link; unrevealed question does not show historical answer.
6. Archive paper/blueprint appearance changes only archive; earned versus locked medals remain identical.
7. Nickname/signature/theme survive reload; selecting a locked medal is impossible.
8. Share preview defaults to no counts/raw questions; opt-in counts and selected earned medals match local SVG output.
9. Mobile viewport has no horizontal overflow, controls and Chinese copy remain readable.
10. Leaving archive returns to original study appearance; no progress or navigation jump caused by saves.
