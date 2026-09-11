# Task 1 report

Status: DONE

## Changed files

- `web/src/domain.js`: added `clampConversationHeight` and `savedConversationHeight` with a 156px minimum, viewport-aware maximum, and local-storage loading.
- `web/src/domain.test.js`: added the required height-clamping and saved-height contract tests.
- `web/src/App.jsx`: added persisted `Conversation` height state, pointer drag finalization, keyboard ArrowUp/ArrowDown resizing, separator accessibility attributes, and CSS custom-property output.
- `web/src/styles.css`: switched the conversation panel to the CSS variable height, added the 10px row-resize separator, and retained scrollable messages.

## TDD evidence

RED command (run from `web/`):

```text
npm test -- --run
```

Result: 2 failed, 7 passed. Both failures were the expected `TypeError: clampConversationHeight is not a function` / `savedConversationHeight is not a function` import-contract failures.

GREEN and build commands (run from `web/`):

```text
npm test -- --run && npm run build
```

Result: Vitest passed 1 file / 9 tests; Vite production build completed successfully. Vite emitted only its existing large-chunk warning.

Additional verification:

```text
git diff --check
```

Result: clean.

## Commit

`01ba8ea70b7344ed8c76e9b009f3208598fe9fb0` (`feat: add resizable compact conversation panel`)

## Self-review

- The implementation is limited to the four files named in the brief.
- The pointer drag updates live without writing storage on every move; pointer-up/pointer-cancel and keyboard adjustments persist the finalized clamped value.
- The separator is keyboard focusable and exposes horizontal-separator semantics.
- The conversation message list retains `overflow-y: auto` and flex sizing so the panel remains compact while messages scroll.

## Concerns

No blocking concerns. The production build reports the pre-existing bundle-size warning for the main JavaScript chunk.
