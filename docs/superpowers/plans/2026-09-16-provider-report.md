# Progressive provider task report

## Scope

- Changed only `app/providers.py`, `app/prompts.py`, and `tests/test_progressive_providers.py` for Task 1.
- Did not read or modify live settings, API keys, or SQLite configuration.
- Preserved the existing `solve_batch` return schema and answer validation behavior.

## Behavior delivered

- Added `ModelGateway.stream_chat(context, text, mode="direct")` as a plain-text async iterator using the existing chat safety/knowledge policy.
- Streaming requests ask for usage frames, ignore valid usage-only SSE chunks, record their token counts, reject truncated streams, and convert malformed frames/network/HTTP failures into safe `ProviderError` categories.
- Vision streaming retains disabled thinking. GLM 5.3 solve/chat/stream requests use `reasoning_effort="low"` and never send disabled thinking.
- Ordinary solve and chat outputs are capped at 4096 tokens; batch solving retains its existing 4096-token cap and independent-question prompt.

## TDD evidence

- RED: `.venv/bin/python -m pytest -q tests/test_progressive_providers.py` → `4 failed, 2 passed` (missing `stream_chat`; ordinary GLM calls lacked `reasoning_effort`).
- Additional RED: `.venv/bin/python -m pytest -q tests/test_progressive_providers.py::test_stream_chat_wraps_wrong_sse_shape_as_safe_schema_error` → `1 failed` with raw `AttributeError`, proving malformed SSE was not safely wrapped.
- GREEN provider suites: `.venv/bin/python -m pytest -q tests/test_progressive_providers.py tests/test_providers.py tests/test_interactions.py` → `32 passed in 5.85s`.
- Full backend verification: `.venv/bin/python -m pytest -q` → `71 passed in 8.08s`.

The bare `pytest` executable was not on `PATH`; all authoritative runs used the repository virtual environment as documented in `README.md`.
