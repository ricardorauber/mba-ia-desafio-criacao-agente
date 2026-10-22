# 0005 - Confirmation protocol over the API

- Date: 2026-10-22
- Spec: 0003, 0005, 0006
- Status: accepted

## Context
ADK's tool confirmation emits an `adk_request_confirmation` function call; a client answers it with a `FunctionResponse` of the same id and name carrying `{"confirmed": bool}`. The challenge needs this over our own API, with `409` for anything not pending in that session.

## Decision
- Tools that charge or release access call `tool_context.request_confirmation(payload=...)` dynamically (the free area does not).
- The pending list is derived from the persisted session events: `adk_request_confirmation` calls without a user function response of the same id. `id` = that call id, `acao` = original tool name, `detalhes` = payload. No separate table, so it survives restarts and cannot diverge from what ADK will resume.
- The confirmation route checks the id against that list under the session lock, then sends the `FunctionResponse` as the new user message; ADK routes it to the authoring agent and re-runs the tool with `tool_context.tool_confirmation`.
- `App` is resumable (`ResumabilityConfig(is_resumable=True)`): the invocation pauses right at the request instead of letting the model keep talking (and possibly re-calling the tool) in the same turn. Experiment: approval worked with a new Runner over the same SQLite file in both modes; the resumable one leaves no extra model turn.

## Consequences
`resposta` may be `""` when a turn stops at a confirmation. A text such as "já confirmei" can never produce a `FunctionResponse`, because the message route only sends text parts.
