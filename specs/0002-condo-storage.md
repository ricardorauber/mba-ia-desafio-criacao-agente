# 0002 - Condo storage and restore

## Goal
Keep reservations and visitor authorizations in a SQLite database whose schema itself guarantees one active reservation per area and date, never reuses a reservation code, and can be restored to the state of `dados/`.

## Scope
- In: `aurora/config.py` (paths), `aurora/storage.py` (schema, seed/restore, read and write operations), the real `aurora-restaurar` command.
- Out: ADK tools (0003), sessions storage (0005), HTTP routes (0005-0007).

## Requirements
- R1: The database SHALL be a SQLite file at `var/aurora.db` (path overridable by the `AURORA_DATA_DIR` environment variable, used by tests), created with its schema on first use.
- R2: The schema SHALL have: `areas(id PK, nome, taxa)`, `apartamentos(numero PK, morador)`, `reservas(codigo PK, apartamento, area, data, cancelada_em NULL)`, `visitantes(id PK autoincrement, apartamento, nome, data)`, `codigos_reserva(codigo PK)` and `sessoes(session_id PK, apartamento, criada_em)`.
- R3: The schema SHALL include the partial unique index `UNIQUE (area, data) WHERE cancelada_em IS NULL` on `reservas`, so exclusivity is enforced by the database at write time.
- R4: The system SHALL load `areas`, `apartamentos`, `reservas` and `visitantes` from the JSON files in `dados/` when the database is created, and register every seed reservation code in `codigos_reserva`.
- R5: `restore()` (and `uv run aurora-restaurar`) SHALL, in one transaction, delete all rows of `reservas` and `visitantes`, reload them from `dados/`, and reload `areas` and `apartamentos`; it SHALL keep `codigos_reserva` and `sessoes` untouched (ADR 0007).
- R6: `create_reservation(apartamento, area, data)` SHALL, inside one `BEGIN IMMEDIATE` transaction, generate a code `RSV-` + 6 characters from `[A-Z0-9]` (via `secrets`), insert it into `codigos_reserva` (retrying with a new code on conflict), and insert the reservation; WHEN the unique index rejects the insert, it SHALL roll back and return a "taken" result instead of raising.
- R7: `cancel_reservation(apartamento, area, data)` SHALL set `cancelada_em` only on an active reservation of that apartment for that area and date, and report whether one was cancelled; it SHALL never touch other apartments' rows.
- R8: The read operations SHALL be: `list_areas()`, `get_area(id)`, `list_reservations(apartamento)` (active only, ordered by date: `codigo`, `area`, `data`), `is_available(area, data)` (bool only), `list_visitors(apartamento)` (ordered by date: `nome`, `data`), `add_visitor(apartamento, nome, data)`, `apartment_exists(numero)`, `save_session(session_id, apartamento)`, `session_apartment(session_id)`.
- R9: Every connection SHALL use `timeout=30` and WAL journal mode, and be opened per operation, so concurrent callers in threads never get "database is locked" under normal load.

## Acceptance criteria
- [ ] AC1: After `uv run aurora-restaurar` on an empty `var/`, `list_reservations("101")` returns exactly `RSV-1377` (quadra, 2030-03-09) and `list_visitors("302")` returns exactly Marina Duarte (2030-03-16). (R1, R4, R5, R8)
- [ ] AC2: A second insert of an active reservation for the same area and date fails at the database level even when done with raw SQL. (R3)
- [ ] AC3: 20 threads calling `create_reservation` for the same area and date result in exactly one success and 19 "taken" results, none raising. (R6, R9)
- [ ] AC4: Codes created never match a seed code nor any previously issued code, including cancelled ones and after a restore. (R5, R6)
- [ ] AC5: `cancel_reservation("101", "salao-de-festas", "2030-03-16")` returns not-cancelled and RSV-4821 stays active. (R7)
- [ ] AC6: After a cancellation, the same area and date can be reserved again. (R3, R7)
- [ ] AC7: Restore keeps `sessoes` and `codigos_reserva` rows. (R5)

## Unit tests
- T1: `tests/test_storage.py::test_seed_matches_dados` (AC1).
- T2: `test_unique_active_reservation_enforced_by_index` (AC2).
- T3: `test_concurrent_create_only_one_wins` with `ThreadPoolExecutor` (AC3).
- T4: `test_codes_never_repeat_after_cancel_and_restore` (AC4, AC7).
- T5: `test_cancel_only_own_reservation` (AC5).
- T6: `test_rebook_after_cancel` (AC6).
