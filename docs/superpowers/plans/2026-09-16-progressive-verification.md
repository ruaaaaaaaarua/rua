# Progressive Study Verification

## Implemented

- Official DeepSeek V4.1 Flash vision configured locally; no credentials in source.
- Session-owned OCR/solve pipeline: first complete question gets an immediate single request; remaining questions form batches of up to three with a shared bounded background pool.
- Correctness is displayed once validated, with explanation hidden until requested. Ready questions remain interactive while later work runs.
- Ordinary chat and expanded explanations stream real content; hint-only responses remain buffered and guarded.
- Separate foreground operation locks, authoritative active session data, help-before-exposure tracking and interrupted-stream cleanup preserve learning records.
- Failed/pending batch items get a bounded single-item fallback; confirmed items are retained on retry.
- Incomplete OCR content remains pending and generates no answer evidence. Explicit completeness acknowledgement is required after editing; a single visible choice remains insufficient.

## Verification (2026-09-16)

- `.venv/bin/python -m pytest -q`: **80 passed**, 8.24 seconds.
- `npm --prefix web test`: **26 passed**, four files.
- `npm --prefix web run build`: succeeded. Existing large-chunk advisory remains (approximately 681 kB main JavaScript bundle).
- `.venv/bin/python -m app.validate_knowledge`: 6 chapters, 18 nodes, 0 published bodies; valid.
- `git diff --check`: clean.
- Independent review identified and verified fixes for batch-pending fallback, first-question identity, incomplete-content acknowledgement and duplicate streaming-user messages.

## Browser Check

Used a separate temporary database and delayed fake provider at port 5173; no fake records inserted into the user's database.

Observed one confirmed question out of four while the other three remained blocked in the fake provider. The first card displayed correctness without disclosing the answer. Reveal and expanded explanation worked during background processing. The first streamed explanation segment appeared immediately; after releasing background work, all four results and the final scoped chat reply remained present. Structural edits were unavailable until background work finished. The test server/tab were removed after verification.

## Real Provider Checks

All calls used configured official endpoints; metrics are observations, not a benchmark or a correctness certification.

- Original supplied HEIC, vision-only run: first complete extracted question **3.57 s**, 8 extracted questions and terminal event in **7.31 s**.
- Two simple synthetic GLM questions in one batch: **2.09 s**, two schema-valid answers.
- Short GLM explanation: first content **0.86 s**, complete **1.37 s**.
- Full real pipeline before OCR completeness adjustment: first confirmed result **6.57 s**, total **33.54 s**, 6 confirmed and 2 pending out of 8. This exposed a misclassified multi-select item and a clipped bottom item; it was not accepted as a clean quality result.
- Full real pipeline after adjustment: first confirmed result **13.36 s**, total **43.92 s**, 5 confirmed and 3 pending out of 8. All questions under the multi-select section inherited the multiple-choice kind; the clipped bottom question was flagged incomplete and withheld from grading. The remaining pending answers require source/condition verification rather than forced confirmation.

Pipeline timing excludes upload and HEIC conversion, and UI polling can add up to roughly one second. Repeated calls vary, and pending results are not successful answers. No claim of all eight answers being correct is made.

## Local Data and Follow-Up Scope

- Owner-only SQLite backup: `data/backups/pre-progressive-20260916.sqlite3`, integrity check passed.
- Personal data, credentials, source photos and backups remain excluded from Git.
- Service restarted on `127.0.0.1:8765`; no user study was processing at restart.
- The user's later ideas about richer review scheduling and combined private-core/personal-history retrieval are recorded for discussion, **not implemented in this change**. Current review baseline remains original-question intervals 1/3/7/14/30 days, with independent/assisted evidence distinctions. Current local Wiki UI is not a production secret-core boundary.
