# 0003 - Domain tools with session-bound apartment and confirmation

## Goal
Expose reservations and visitors to the agents only through ADK tools that take the apartment from the session, never from the model, and that pause any charge or access release until the system confirmation arrives.

## Scope
- In: `aurora/tools.py` with the reservation and visitor tools; a scripted fake LLM for tests in `tests/fakes.py`.
- Out: agent wiring (0004), HTTP confirmation route (0006), regulation (0004).

## Requirements
- R1: Every tool SHALL obtain the apartment from `tool_context.user_id` (the ADK session's user id, set by the server at session creation, ADR 0006); no tool SHALL have an apartment parameter.
- R2: Every tool SHALL accept the area as its id or its name (case- and accent-insensitive, e.g. "salão de festas" → `salao-de-festas`) and the date as `AAAA-MM-DD`; invalid values SHALL return `{"status": "erro", "mensagem": ...}` in PT-BR listing the valid areas or the expected format, without touching data.
- R3: `listar_areas()` SHALL return `id`, `nome`, `taxa` and `gera_cobranca` of every area.
- R4: `listar_minhas_reservas()` SHALL return only the session apartment's active reservations (`codigo`, `area`, `nome_area`, `data`).
- R5: `verificar_disponibilidade(area, data)` SHALL return only `area`, `data` and `disponivel` (bool) — never who holds the date.
- R6: `reservar_area(area, data)` SHALL: (a) return `{"status": "indisponivel"}` without asking confirmation when the date is already taken; (b) for an area with `taxa > 0` and no confirmation yet, call `tool_context.request_confirmation(hint=..., payload={"area": <id>, "nome_area": ..., "data": ..., "taxa": ...})` and return `{"status": "aguardando_confirmacao"}` without writing; (c) WHEN the confirmation is rejected, return `{"status": "nao_confirmada"}` without writing; (d) for `taxa == 0`, or after an approved confirmation, call `create_reservation` and return `{"status": "reservada", "codigo", "area", "data", "taxa"}` or `{"status": "indisponivel"}` when the database rejects it.
- R7: `cancelar_reserva(area, data)` SHALL cancel only the session apartment's active reservation for that area and date, without confirmation, and return `{"status": "cancelada", "codigo", ...}` or `{"status": "nao_encontrada"}`; the not-found message SHALL NOT say whether another apartment holds the date.
- R8: `listar_meus_visitantes()` SHALL return only the session apartment's visitors (`nome`, `data`).
- R9: `autorizar_visitante(nome, data)` SHALL always request confirmation first (payload `{"nome": <trimmed>, "data": ...}`), whatever the conversation says; only after an approved confirmation it SHALL call `add_visitor` and return `{"status": "autorizado", "nome", "data"}`; rejection returns `{"status": "nao_confirmada"}`. Names SHALL be trimmed, non-empty and at most 80 characters.
- R10: Storage calls SHALL run in a worker thread (`asyncio.to_thread`) so a write never blocks the event loop.
- R11: No tool output SHALL contain another apartment's number, reservation codes or visitor names.

## Acceptance criteria
- [ ] AC1: With a session of apartment 101, every tool reads/writes rows of 101 only, and `inspect.signature` of every tool has no apartment-like parameter. (R1, R11)
- [ ] AC2: "Salão de Festas", "salao de festas" and `salao-de-festas` resolve to the same id; an unknown area returns the error listing the three areas. (R2, R3)
- [ ] AC3: `verificar_disponibilidade("salao-de-festas", "2030-03-16")` returns `disponivel: false` and its JSON has no `302` nor `RSV-4821`. (R5, R11)
- [ ] AC4: `reservar_area` on `quadra` writes immediately with no confirmation request; on `salao-de-festas` it requests confirmation with area and date in the payload and writes nothing until approved; rejection writes nothing. (R6)
- [ ] AC5: `reservar_area("salao-de-festas", "2030-03-16")` returns `indisponivel` without requesting confirmation and without leaking the holder. (R6, R11)
- [ ] AC6: `cancelar_reserva("salao-de-festas", "2030-03-16")` from 101 returns `nao_encontrada` and RSV-4821 stays. (R7)
- [ ] AC7: `autorizar_visitante` always requests confirmation with name and date in the payload, and writes only after approval. (R9)

## Unit tests
- T1: `tests/test_tools.py` drives each tool through a real ADK `Runner` with the scripted fake LLM of `tests/fakes.py` and an in-memory session (AC1-AC7), answering confirmations with an `adk_request_confirmation` FunctionResponse.
- T2: `test_tools_have_no_apartment_parameter` (AC1).
- T3: `test_area_aliases` (AC2).
