# 0007 - Verification routes

## Goal
Let the evaluator read reservations and visitors of an apartment straight from storage, without the model.

## Scope
- In: `GET /apartamentos/{numero}/reservas` and `GET /apartamentos/{numero}/visitantes` in `aurora/api.py`.
- Out: authentication of these routes (out of scope of the challenge).

## Requirements
- R1: `GET /apartamentos/{numero}/reservas` SHALL return `200` with the apartment's active reservations ordered by date, each `{"codigo", "area", "data"}`.
- R2: `GET /apartamentos/{numero}/visitantes` SHALL return `200` with the apartment's visitors ordered by date, each `{"nome", "data"}`.
- R3: An apartment not in `dados/apartamentos.json` SHALL return `404` (free behavior, chosen for clarity).
- R4: Cancelled reservations SHALL NOT be listed.

## Acceptance criteria
- [ ] AC1: With restored data, `/apartamentos/101/reservas` returns exactly `[{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}]` and `/apartamentos/302/visitantes` returns exactly `[{"nome": "Marina Duarte", "data": "2030-03-16"}]`. (R1, R2)
- [ ] AC2: `/apartamentos/999/reservas` returns `404`. (R3)
- [ ] AC3: After cancelling RSV-1377 in storage, `/apartamentos/101/reservas` returns `[]`. (R4)

## Unit tests
- T1: `tests/test_verification.py` (AC1-AC3).
