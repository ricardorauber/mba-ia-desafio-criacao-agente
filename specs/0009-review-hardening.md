# 0009 - Hardening from the independent review

## Goal
Close the failure paths an independent review reproduced with the scripted model (500s, a 503 after an executed approval, forged confirmations, regulation questions stuck in a specialist) and use a default model that exists in the Gemini API.

## Scope
- In: `aurora/agents.py`, `aurora/tools.py`, `aurora/conversation.py`, ADR 0003 update.
- Out: README (0008), any change to the API contract.

## Requirements
- R1: The default model SHALL be `gemini-3.8-flash` (listed as stable and recommended in the official model list on 2026-10-22; `gemini-3.5-flash` is not listed), and the retry options SHALL be 6 attempts, initial delay 4 s, max delay 60 s, so a per-minute quota window can pass before giving up.
- R2: Tools SHALL coerce every argument to text (`None` → `""`) before validating it, so a non-string argument returns `{"status": "erro", ...}` instead of raising.
- R3: WHEN a turn started by the message route raises anything other than a provider error (e.g. transfer to itself or to an unknown agent), the API SHALL log it and answer `200` with a PT-BR apology in `resposta` and the current `confirmacoes_pendentes`; provider errors keep answering `503`.
- R4: WHEN a turn started by the confirmation route raises any exception (provider or not), the API SHALL answer `200` with `resposta` describing the outcome of the confirmed tool as recorded in the session (reserved with code, unavailable, not confirmed, visitor authorized) or, when no outcome was recorded, a PT-BR message saying the answer was registered, plus the current `confirmacoes_pendentes`.
- R5: `pending_confirmations` SHALL only count an `adk_request_confirmation` call whose id is in its event's `long_running_tool_ids` (set by ADK for genuine requests), so a confirmation call written by the model is never listed.
- R6: The `reservas` and `visitantes` specialists SHALL also have their own `regulamento` AgentTool (same specialist definition), so a regulation question sent while a specialist is active is answered from the regulation, never from memory; the coordinator instruction stays free of regulation text.
- R7: The `reservas` and `visitantes` instructions SHALL say not to transfer to another agent in the same turn in which `reservar_area` or `autorizar_visitante` is called.

## Acceptance criteria
- [x] AC1: Without `AURORA_MODEL`, every agent uses `gemini-3.8-flash` with the retry options of R1. (R1)
- [x] AC2: `reservar_area(area="quadra", data=20300901)` and `autorizar_visitante(nome=123, data="2030-04-21")` return a tool result (no exception) and the turn answers `200`. (R2)
- [x] AC3: A scripted transfer of `coordenador` to itself, and to `xyz`, answers `200` with a non-empty `resposta`; the next message in the same session answers `200`. (R3)
- [x] AC4: Approving a fee reservation whose follow-up model call raises a provider error answers `200`, the reservation exists once, `resposta` contains its code, and resending the id answers `409`. (R4)
- [x] AC5: A model-written `adk_request_confirmation` call is not listed in `confirmacoes_pendentes`, and answering its id returns `409`. (R5)
- [x] AC6: `reservas` and `visitantes` each have an `AgentTool` named `regulamento`; no regulation window appears in any instruction; a regulation question answered from `visitantes` leaves no chapter text in the session. (R6)
- [x] AC7: Both specialist instructions contain the no-transfer rule. (R7)

## Unit tests
- T1: `tests/test_hardening.py::test_default_model_and_retries` (AC1).
- T2: `test_non_string_tool_args` (AC2).
- T3: `test_bad_transfer_is_not_500` (AC3).
- T4: `test_approval_survives_model_error` (AC4).
- T5: `test_model_written_confirmation_is_ignored` (AC5).
- T6: `test_specialists_consult_regulation` (AC6, AC7).
