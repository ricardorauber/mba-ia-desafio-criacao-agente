# 0001 - Project setup and conventions

## Goal
Give the Residencial Aurora assistant a pinned, reproducible uv project skeleton, a test setup and the repository conventions every later spec relies on.

## Scope
- In: `pyproject.toml` + `uv.lock`, the empty package `aurora/` (with `__init__.py`), the console scripts stubs `aurora-api` and `aurora-restaurar`, `.env.example`, `.gitignore` additions, `tests/` with a smoke test, the conventions below.
- Out: storage (0002), tools (0003), agents (0004), API (0005-0007), README content (0008).

## Conventions (apply to every spec)
- Code, specs, ADRs and commit messages in American English; every text a resident or the evaluator reads (agent instructions, tool messages, API error details, README) in Brazilian Portuguese (ADR 0001).
- Each spec is built in its own branch and `main` is fast-forwarded after it is green (ADR 0002).
- The files under `dados/` are never modified.
- Runtime data lives under `var/` (ignored by git).

## Requirements
- R1: The project SHALL require Python `>=3.12` and be managed by uv, with `pyproject.toml` and `uv.lock` versioned.
- R2: Every direct dependency SHALL be pinned with `==`: `google-adk==2.12.0`, `fastapi`, `uvicorn` and `python-dotenv` at the versions uv resolves together with ADK 2.12.0; dev group `pytest`, `pytest-asyncio` and `httpx` pinned the same way.
- R3: The project SHALL expose two console scripts: `aurora-api` (entry `aurora.main:run_api`) and `aurora-restaurar` (entry `aurora.main:run_restore`); in this spec both are stubs that print a line and exit 0.
- R4: `.env.example` SHALL list, without values, `GOOGLE_API_KEY=`, `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, and `AURORA_MODEL=` (empty means the default model of spec 0004); `.env` SHALL stay ignored by git.
- R5: `.gitignore` SHALL also ignore `var/`, `.pytest_cache/` and `*.db`.
- R6: `uv run pytest` from the repository root SHALL discover `tests/` with `asyncio_mode = "auto"`.
- R7: No file under `dados/` SHALL differ from the starter commit `be87e1d`.

## Acceptance criteria
- [ ] AC1: `uv sync` in a clean clone succeeds and `uv.lock` pins `google-adk` at `2.12.0`. (R1, R2)
- [ ] AC2: Every entry of `[project].dependencies` and of the dev group uses `==`. (R2)
- [ ] AC3: `uv run aurora-api` and `uv run aurora-restaurar` exit 0 (stubs). (R3)
- [ ] AC4: `.env.example` has exactly the variables of R4 with no secret value, and `git check-ignore .env var/x.db` succeeds. (R4, R5)
- [ ] AC5: `uv run pytest` collects and passes the smoke test. (R6)
- [ ] AC6: `git diff --stat be87e1d -- dados` is empty. (R7)

## Unit tests
- T1: `tests/test_smoke.py` imports `aurora` and asserts `google.adk.__version__ == "2.12.0"` (AC1, AC5).
