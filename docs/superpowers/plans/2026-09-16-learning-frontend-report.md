# Personal learning frontend report

## Implemented

- Rebuilt reviews around knowledge/method groups, representative questions, estimated difficulty/reason copy, 3/5/10 recommendation budgets, full-original access, explicit bounded organization progress, review hints, and stable completed-run handling.
- Added controlled manual classification correction from original questions using the server taxonomy and personally visible knowledge IDs. Validation requires target/method/boundary conditions and labels confidence/difficulty/reason as estimates rather than authority.
- Tightened personal Wiki privacy: linked-node empty state, linked published/draft handling, no static unlinked dashboard preview, optional references, and no ordinary source/model badge chrome. Related personal history appears only inside a revealed answer and opens the exact original session/question.
- Added the focused archive modules `Archive.jsx`, `archive.js`, and `archive.css`: scoped paper/blueprint themes, profile editing, three distinct inline vector medals, evidence/locked states, up-to-three earned selection, immediate preview, persistence feedback, and refresh-after-rejected-save behavior.
- Added a self-contained SVG share card that escapes user text, filters locked medals, defaults aggregate stats off, contains no scripts/foreignObject/external assets, downloads through Blob/Object URL with revocation, and uses mixed CJK/Latin width budgeting with wrapping/truncation shared by preview and export.
- Kept archive saves on the current page. Editing any draft field, theme, stats choice, or medal clears stale success feedback. A rejected medal save reloads actual server eligibility instead of retaining an earned-looking client draft.

## Actual API usage

- `GET /api/reviews?limit=3|5|10`
- `GET /api/review-taxonomy`
- `POST /api/reviews/organize` (explicit action only; no polling)
- `POST /api/reviews/start`, `POST /api/reviews/{rid}/hint`, `POST /api/reviews/{rid}/reveal`, `POST /api/reviews/{rid}/answer`
- `PATCH /api/sessions/{sid}/questions/{qid}/classification`
- Existing scoped `GET /api/wiki` and `GET /api/wiki/{kid}`
- `GET /api/archive`, `PUT /api/archive`

No dependency was added, no live model/provider call was made, and no user database was changed by this frontend task.

## TDD evidence

### RED

Initial focused command:

```text
npm --prefix web test -- src/Archive.test.jsx src/Reviews.test.jsx src/Study.test.jsx
```

Expected failures:

```text
Archive.test.jsx: Cannot find module './Archive.jsx'
Reviews.test.jsx: expected rendered output to contain '知识·方法组'
Reviews.test.jsx: buildClassification is not a function
Test Files 2 failed | 1 passed
Tests 2 failed | 9 passed
```

The failures showed that the archive module, grouped review UI, and correction payload builder did not yet exist.

A later width-safety test also failed as expected before the exporter was corrected:

```text
Archive.test.jsx > wraps long mixed-width text within the card and truncates with an ellipsis
expected SVG to contain '<tspan'
Tests 1 failed | 4 passed
```

The stale-save-feedback test initially failed because `changeArchiveProfile` was not implemented, then passed after the helper was connected to every archive draft mutation.

### GREEN

Focused archive verification:

```text
npm --prefix web test -- src/Archive.test.jsx
Test Files 1 passed (1)
Tests 7 passed (7)
```

Full frontend regression:

```text
npm --prefix web test
Test Files 6 passed (6)
Tests 43 passed (43)
```

Production build:

```text
npm --prefix web run build
✓ 2136 modules transformed
✓ built
```

Build warning: Vite reports the existing single JavaScript chunk is larger than 500 kB after minification. The build succeeds; no dependency or routing split was introduced in this scoped task.

`git diff --check` completed without whitespace errors.

## Files changed

- `web/src/Archive.jsx`, `web/src/archive.js`, `web/src/archive.css`, `web/src/Archive.test.jsx`
- `web/src/Reviews.jsx`, `web/src/Reviews.test.jsx`
- `web/src/App.jsx`, `web/src/Knowledge.jsx`, `web/src/Study.jsx`, `web/src/Study.test.jsx`
- `web/src/api.js`, `web/src/api.test.js`, `web/src/domain.js`, `web/src/styles.css`, `web/src/ui.jsx`
- This report.

## Self-review

- Confirmed no group-level completion claim is shown and no representative mutates or visually passes siblings.
- Confirmed organize is an explicit single request, explains the temporary write lock, preserves the page, and reports classified/failed/remaining counts.
- Confirmed archive CSS themes are rooted under `.archive-root`, mobile/reduced-motion styles are present, locked/empty states make no earned claim, and share output excludes raw questions/images/right-rate.
- Confirmed related history is capped at two, hidden before reveal, and navigates with the existing `openSession(sid, qid)` integration.
- Confirmed optional Wiki metadata uses safe fallbacks.

## Concerns

- Browser visual/interaction QA is intentionally left to the controller's isolated fixture, per task assignment.
- The successful build retains the pre-existing large-chunk warning described above.

## Post-review correction wave

Controller review found five contract/visual issues. New failing tests reproduced them before fixes: the initial review view rendered all groups instead of the bounded `recommended` list; unlinked citations were clickable; explicit blank archive text gained stock copy; failed save plus failed eligibility reload could retain unsafe client selection without a local error; and SID/QID URL segments were not encoded. A browser check also showed the SVG signature width budget was based on characters rather than rendered pixels.

Focused RED before this correction wave: 5 failures across `Reviews.test.jsx`, `Study.test.jsx`, `Archive.test.jsx`, and `api.test.js`. The additional save-failure-plus-refresh-failure test then failed because `recoverRejectedArchive` did not exist. After implementation, the full suite is 43/43 passing.

Corrections now:

- Render only server-bounded recommendations in the initial “知识·方法组” view, with a separate “全部分组” tab and the existing “全部原题” tab.
- Render citations as links only when their IDs are in the mounted personal Wiki set; otherwise retain plain reference text.
- Preserve explicit blank nickname/signature, remove stock signature export copy, and use a 520px-safe weighted CJK/Latin budget (13 units at 38px for nickname; 29 units at 17px for signature).
- Clear rejected medal selections immediately; if the corrective archive GET also fails, keep the safe selection, disable medal choice, and show an inline eligibility-refresh error.
- Label medal descriptions as earning conditions and list available evidence records consistently.
- Encode dynamic session/question/review URL path segments.
- Translate raw review difficulty codes and normalize trailing punctuation in recommendation reasons.
