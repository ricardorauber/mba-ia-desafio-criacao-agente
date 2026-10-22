# 0004 - Agent topology: transfer for actions, AgentTool for the regulation

- Date: 2026-10-22
- Spec: 0004
- Status: accepted

## Context
The resident talks to one main agent; at least two specialists are required. Two needs pull in different directions:
- Confirmation must resume in the agent that asked for it, and that request must live in the persisted session. An `AgentTool` runs its agent in a separate in-memory session, so a confirmation raised inside it would be lost on restart.
- The regulation must not enter the session history. Experiment (ADK 2.12.0, SQLite session): the inner events of an `AgentTool` — including its tools' responses — are not stored in the caller's session; only the final answer is.

## Decision
- `coordenador` (root): routes the conversation.
- `reservas` and `visitantes`: `sub_agents` reached by `transfer_to_agent`. Their tool calls and confirmation requests are events of the resident's session, so the Runner routes the confirmation answer back to them (`_agent_router.find_agent_to_run`, verified to work with a fresh Runner over the same SQLite file).
- `regulamento`: `AgentTool` of the coordinator, with `listar_capitulos` and `ler_capitulo`. The chapter text stays in its ephemeral session; the resident's session only gets the specific answer.

## Consequences
After a specialist answers, the next message starts in it (ADK keeps the last transferable agent); specialists transfer back to `coordenador` for other topics, costing one extra model call in that case.
