# 0007 - Restore resets condo data only

- Date: 2026-10-22
- Spec: 0002
- Status: accepted

## Context
The restore command must bring reservations and visitors back to `dados/`; wiping sessions is optional. Codes must never repeat, including cancelled ones.

## Decision
`aurora-restaurar` rewrites `reservas`, `visitantes`, `areas` and `apartamentos` from `dados/` in one transaction and keeps `sessoes`, `codigos_reserva` and `var/sessoes.db`. Every issued code stays in `codigos_reserva` forever, so a code issued before a restore is never issued again.

## Consequences
Old sessions keep working after a restore; their history may mention reservations that no longer exist, which is the expected effect of a data reset.
