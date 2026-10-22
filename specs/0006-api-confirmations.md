# 0006 - API: answering confirmations

## Goal
Let the resident approve or reject a pending action only through the confirmation route, resuming the agent that asked for it, executing an approved action exactly once and rejecting any other id with `409`.

## Scope
- In: route `POST /sessoes/{session_id}/confirmacoes` in `aurora/api.py`, resume helper in `aurora/conversation.py`.
- Out: everything else.

## Requirements
- R1: The route SHALL accept `{"id": str, "confirmado": bool}` and answer `404` when the session does not exist.
- R2: WHEN `id` is not in the session's pending confirmations (spec 0005 R3) — unknown, from another session, or already answered — the route SHALL answer `409` with a PT-BR `detail` and run nothing.
- R3: Otherwise it SHALL send to the `Runner` a user message whose only part is `FunctionResponse(id=<id>, name="adk_request_confirmation", response={"confirmed": <confirmado>})`, so the ADK router resumes the agent that authored the request (ADR 0005), and answer `200` in the same shape as the message route.
- R4: The pending check and the resume SHALL run under the session's lock (spec 0005 R7), so a sequential resend of the same id always sees it answered and gets `409`.
- R5: Approving SHALL execute the action once; rejecting SHALL change no data; the outcome SHALL also hold after an API restart between the request and the answer.

## Acceptance criteria
- [x] AC1: With the fake LLM: request a fee reservation, answer `confirmado: false` → `200`, no reservation; request again, answer `true` → `200`, exactly one reservation; resend the same id → `409`, still one. (R2, R3, R5)
- [x] AC2: `{"id": "id-inexistente", ...}` → `409` and reservations unchanged. (R2)
- [x] AC3: The id of a pending confirmation of session A sent to session B → `409`. (R2)
- [x] AC4: Recreating the app between the request and the approval still executes the reservation once. (R5)
- [x] AC5: Two sessions (101 and 201) with pending confirmations for the same area and date approved concurrently (`asyncio.gather`) both return `200` and the two apartments sum exactly one reservation. (R3, R5)
- [x] AC6: A visitor authorization appears in storage only after approval. (R3, R5)

## Unit tests
- T1: `tests/test_confirmations.py` covering AC1-AC6 with `httpx.ASGITransport` and the fake LLM.
