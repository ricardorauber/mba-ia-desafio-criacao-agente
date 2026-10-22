# 0005 - API: sessions, messages and events

## Goal
Expose the assistant through FastAPI with persisted ADK sessions, following the challenge contract for creating sessions, sending messages and reading events.

## Scope
- In: `aurora/api.py` (FastAPI app, lifespan with `Runner` and `SqliteSessionService` at `var/sessoes.db`), `aurora/conversation.py` (run a turn, collect the reply text, compute pending confirmations), routes `POST /sessoes`, `POST /sessoes/{session_id}/mensagens`, `GET /sessoes/{session_id}/eventos`, the real `aurora-api` command.
- Out: confirmation route (0006), verification routes (0007).

## Requirements
- R1: `POST /sessoes` with `{"apartamento": "101"}` SHALL create an ADK session with `user_id` = the apartment and state `{"apartamento": ...}`, record it in `sessoes`, and answer `201 {"session_id": ...}`; an apartment not in `dados/apartamentos.json` SHALL get `422` (free behavior, chosen for safety).
- R2: `POST /sessoes/{session_id}/mensagens` with `{"texto": ...}` SHALL run one turn and answer `200 {"resposta": str, "confirmacoes_pendentes": [...]}`; `resposta` is the text parts (non-thought, non-partial) authored by agents in this turn joined by blank lines, possibly `""`.
- R3: `confirmacoes_pendentes` SHALL list every `adk_request_confirmation` function call in the session's events without a matching user function response, in order, as `{"id": <function call id>, "acao": <original tool name>, "detalhes": <toolConfirmation.payload>}`.
- R4: `GET /sessoes/{session_id}/eventos` SHALL return `200` with every stored event in order, each as `event.model_dump(mode="json", exclude_none=True)`.
- R5: Every route with `{session_id}` SHALL answer `404` when the session does not exist.
- R6: Sessions and condo data SHALL survive a restart: the API reopens the same `var/` files, and a session created before keeps its events and accepts new messages.
- R7: Turns of the same session SHALL be serialized by a per-session `asyncio.Lock`; different sessions run concurrently.
- R8: Model/provider failures after retries SHALL answer `503` with a PT-BR `detail`, never a raw `500`.
- R9: `uv run aurora-api` SHALL load `.env` and serve on `127.0.0.1:8000` with a single worker.

## Acceptance criteria
- [ ] AC1: `POST /sessoes` returns `201` and a `session_id`; `POST /sessoes` with an unknown apartment returns `422`. (R1)
- [ ] AC2: With the fake LLM, a message returns `200` with the contract shape and the reply text. (R2)
- [ ] AC3: A fee reservation leaves one item in `confirmacoes_pendentes` with `acao`, `detalhes.area` and `detalhes.data`. (R3)
- [ ] AC4: `GET /sessoes/sessao-inexistente/eventos` and `POST /sessoes/sessao-inexistente/mensagens` return `404`. (R5)
- [ ] AC5: After recreating the app over the same `var/` (restart), `GET /eventos` returns the same number of events and a new message returns `200` and increases it. (R4, R6)
- [ ] AC6: A provider error raised by the model returns `503`. (R8)

## Unit tests
- T1: `tests/test_api.py` with `httpx.ASGITransport` and the fake LLM (AC1-AC6), each test with its own `AURORA_DATA_DIR` under `tmp_path`.
