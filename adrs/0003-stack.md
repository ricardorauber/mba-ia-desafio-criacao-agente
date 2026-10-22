# 0003 - Stack: ADK 2.12.0, FastAPI and SQLite

- Date: 2026-10-22
- Spec: 0001, 0002, 0004, 0005
- Status: accepted

## Context
The challenge requires Python 3.12+, uv, Google ADK 2.x (>= 2.2.0, exact pin) and Gemini through Google AI Studio; framework and storage are free, and anything external must start with a documented command.

## Decision
- `google-adk==2.12.0`, the latest 2.x release at build time; FastAPI and uvicorn, already dependencies of ADK.
- SQLite for everything, two files under `var/`: `aurora.db` (condo data, our schema) and `sessoes.db` (ADK `SqliteSessionService`, which needs no SQLAlchemy). No container, nothing to start besides the API.
- One model for all agents, `AURORA_MODEL`, default `gemini-3.5-flash`, with ADK retry options (5 attempts) to absorb transient 429/5xx. To be confirmed against the user's AI Studio project in spec 0008.

## Consequences
Zero external services. SQLite serializes writers, which is enough for the evaluator's load and gives the partial unique index used for Guarantee 5.
