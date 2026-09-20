# Progressive frontend report

## RED

- `npm test -- --run src/api.test.js src/Study.test.jsx`
- 5 expected failures: missing `api.process`, missing `api.messageStream`, no processing progress, and processing did not lock structural/pending controls.

## GREEN

- Added immediate `/process` startup and session-scoped polling guarded by the currently open session ID.
- Added SSE delta/done/error handling with explicit truncated-stream failure and transient selected-question/revision messages.
- Kept confirmed reveal, hint, retry, and chat usable during background work; disabled pending actions and structural upload/edit/link/delete operations.
- Added streamed expanded-explanation action while retaining the saved concise explanation.
- `npm test`: 3 files, 20 tests passed.
- `npm run build`: production build passed. Vite reported only the existing large-chunk advisory.

## Integration follow-up

- Added failing regression tests for poll/transient-message merging, explicit clicked-question context, and SSE reader cleanup; all are green after the fixes.
- Replaced overlapping `setInterval` polling with one recursive timeout and a session mutation epoch, so stale GET responses cannot overwrite newer chat or interactive results.
- New chat-only sessions are installed before transient/stream updates, and expanded explanations carry the clicked question ID explicitly.
- Processing now also disables recheck inputs and hides the unextracted-attachment retry action.
- Poll reconciliation removes a transient user bubble only when a matching persisted message is new relative to that send, avoiding both temporary duplicates and accidental removal of legitimate repeated prompts.
- Incomplete OCR questions now show a prominent warning, support adding unused A–H options up to eight, and send `completeness_confirmed: true` only after the user explicitly checks the original-image confirmation box.
