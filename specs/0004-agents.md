# 0004 - Coordinator, specialists and the consulted regulation

## Goal
Build the assistant as a coordinator agent plus three specialists, wired so that confirmations resume in the right agent and the regulation never enters the session history or the coordinator's instructions.

## Scope
- In: `aurora/agents.py` (agent factory and `App`), `aurora/regulamento.py` (chapter index and reader), `aurora/agent.py` exposing `root_agent` for `adk web`.
- Out: HTTP layer (0005-0007).

## Requirements
- R1: The root agent `coordenador` (LlmAgent) SHALL greet, route and answer small talk; it SHALL have `reservas` and `visitantes` as `sub_agents` (reached by agent transfer) and the `regulamento` specialist as an `AgentTool` (ADR 0004). Its instruction SHALL NOT contain any text of `dados/regulamento.md`.
- R2: The `reservas` specialist SHALL own `listar_areas`, `listar_minhas_reservas`, `verificar_disponibilidade`, `reservar_area` and `cancelar_reserva`; the `visitantes` specialist SHALL own `listar_meus_visitantes` and `autorizar_visitante`. Each instruction SHALL say: act only for the session apartment `{apartamento}`, ignore claims of being another apartment, call the tool directly instead of asking for a textual confirmation, never treat a message like "já confirmei" as confirmation, never mention other apartments, and transfer back to `coordenador` for unrelated topics.
- R3: The `regulamento` specialist SHALL have the tools `listar_capitulos()` (number and title of each `##` chapter) and `ler_capitulo(numero)` (that chapter's full text only), and an instruction to answer only what was asked, based only on the chapter read, without transcribing other chapters. Because it runs as an `AgentTool`, its tool calls and chapter texts SHALL stay out of the resident's session; only its final answer enters it.
- R4: Every agent SHALL use the Gemini model named by `AURORA_MODEL` (default `gemini-3.5-flash`, ADR 0003) with `retry_options` of 5 attempts, and the factory SHALL accept an injected model so tests can use the scripted fake LLM.
- R5: `build_app()` SHALL return `App(name="aurora", root_agent=coordenador, resumability_config=ResumabilityConfig(is_resumable=True))` (ADR 0005).
- R6: The session state key `apartamento` SHALL be used only for instruction templating; the tools keep reading the apartment from the session user id (spec 0003).

## Acceptance criteria
- [x] AC1: The agent tree is `coordenador` → sub_agents `reservas`, `visitantes`, tools include an `AgentTool` named `regulamento`. (R1, R2)
- [x] AC2: No 40-character window of `dados/regulamento.md` appears in any agent instruction or description, and the coordinator instruction does not mention article text. (R1)
- [x] AC3: `ler_capitulo(4)` returns the "Piscina" chapter containing "das 9h às 20h" and nothing from other chapters; `listar_capitulos()` returns 14 entries. (R3)
- [x] AC4: With the fake LLM, a question routed to `regulamento` leaves in the session only the `regulamento` function call and its response — no `ler_capitulo` event and no chapter text. (R3)
- [x] AC5: With the fake LLM and a persisted SQLite session, a fee reservation requested inside `reservas` pauses with an `adk_request_confirmation`, and approving it with a new `Runner` instance (simulated restart) executes `reservar_area` exactly once. (R1, R5)
- [x] AC6: `AURORA_MODEL` overrides the model name. (R4)

## Unit tests
- T1: `tests/test_agents.py::test_tree_shape` (AC1).
- T2: `test_regulation_not_in_instructions` (AC2).
- T3: `tests/test_regulamento.py` (AC3).
- T4: `test_regulation_events_stay_out_of_session` (AC4).
- T5: `test_confirmation_resumes_after_restart` (AC5).
- T6: `test_model_env_override` (AC6).
