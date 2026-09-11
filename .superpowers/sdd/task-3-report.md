# Task 3 Report: Safe failure kinds and profile concurrency

## Implemented

- `ProviderError` carries a safe `error_kind`; provider call telemetry records it on failed calls without saving raw prompts, responses, or credentials.
- Rate-window usage is keyed by SHA-256 of the configured account identity (`base_url`, `model`, `api_key`), isolating distinct provider accounts.
- `ModelGateway.parallel_for(task)` uses the selected task profile's `parallel` value before the legacy global value, then defaults to one. Analysis uses that gateway policy and preserves the legacy fallback for test/custom gateways without the new method.
- Profiles accept an optional validated `parallel` value from 1 to 8, and the settings modal exposes it as “并发上限”. Task selectors are unchanged, including the user-configured `chat` profile route.
- Added tests for safe schema-failure telemetry, per-profile precedence, distinct account rate keys, and record redaction.

## Verification

- Focused Task 3 tests: `4 passed`
- `./.venv/bin/pytest -q`: `59 passed`
- `npm --prefix web test -- --run`: `11 passed`
- `npm --prefix web run build`: passed (existing bundle-size advisory only)
- `git diff --check`: passed

## Review note

Independent review found no critical or important issues. Low-priority follow-up: streaming HTTP failures currently use the general rejection category rather than splitting rate-limit/unavailable categories as non-stream calls do; broader fallback/bounds test coverage would also be useful.

## Controller review follow-up

- `Store.record_call` now normalizes every supplied error category against the provider safe-category allowlist before persistence; arbitrary text is replaced by `provider_error`.
- Semantic response-schema rejections now participate in `_call` telemetry before the observer runs. Empty extraction, invalid batched answer entries, generated-purpose mismatches, and verification-answer mismatches all record `success: false` with `error_kind: response_schema`.
- Added focused regressions for both boundaries.

### Follow-up verification

- Focused regressions: `4 passed`
- `./.venv/bin/pytest -q`: `61 passed`
- `npm --prefix web test -- --run`: `11 passed`
- `npm --prefix web run build`: passed (existing bundle-size advisory only)
- `git diff --check`: passed

## Final index-boundary follow-up

- Nonnegative batched solution indices outside the submitted question range now become a `response_schema` telemetry failure before observer delivery and are omitted from returned batch results.
- Added a focused regression for this boundary.

### Final verification

- Focused index regression plus related batch telemetry tests: `3 passed`
- `./.venv/bin/pytest -q`: `62 passed`
- `npm --prefix web test -- --run`: `11 passed`
- `npm --prefix web run build`: passed (existing bundle-size advisory only)
- `git diff --check`: passed
