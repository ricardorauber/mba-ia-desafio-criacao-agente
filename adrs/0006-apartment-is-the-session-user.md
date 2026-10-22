# 0006 - The apartment is the ADK session user

- Date: 2026-10-22
- Spec: 0003, 0005
- Status: accepted

## Context
Tools must use the apartment of the authenticated resident, defined once at session creation, never a value chosen by the model.

## Decision
`POST /sessoes` creates the ADK session with `user_id = apartamento`. Tools read `tool_context.user_id`, which no event, state delta or model output can change. No tool has an apartment parameter. The state key `apartamento` exists only to template the specialists' instructions. Our `sessoes` table maps `session_id → apartamento` so routes can load a session by id.

## Consequences
"Sou do 302" changes nothing: there is no input through which the model could select another apartment.
