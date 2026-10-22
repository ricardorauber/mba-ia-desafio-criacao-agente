# 0003 - Stack: ADK 2.12.0, FastAPI and SQLite

- Date: 2026-10-22
- Spec: 0001, 0002, 0004, 0005
- Status: accepted

## Context
The challenge requires Python 3.12+, uv, Google ADK 2.x (>= 2.2.0, exact pin) and Gemini through Google AI Studio; framework and storage are free, and anything external must start with a documented command.

## Decision
- `google-adk==2.12.0`, the latest 2.x release at build time; FastAPI and uvicorn, already dependencies of ADK.
- SQLite for everything, two files under `var/`: `aurora.db` (condo data, our schema) and `sessoes.db` (ADK `SqliteSessionService`, which needs no SQLAlchemy). No container, nothing to start besides the API.
- One model for all agents, `AURORA_MODEL`, default `gemini-3.8-flash`, with ADK retry options (6 attempts, 4 s initial delay, 60 s max delay) to absorb transient 429/5xx.
- Update (spec 0009): the first default, `gemini-3.5-flash`, is not in the official list of stable models (checked on 2026-10-22 at ai.google.dev/gemini-api/docs/models); `gemini-3.8-flash` is listed as stable and recommended for new projects. It was not exercised against a real key (ADR 0008).

## Consequences
Zero external services. SQLite serializes writers, which is enough for the evaluator's load and gives the partial unique index used for Guarantee 5.
