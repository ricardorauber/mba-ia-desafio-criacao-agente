# 0001 - User-facing text in Brazilian Portuguese

- Date: 2026-10-22
- Spec: all
- Status: accepted

## Context
The residents, the evaluator and the challenge statement speak Brazilian Portuguese, while the SDD artifacts follow the convention of the previous challenges.

## Decision
Code identifiers, specs, ADRs and commit messages are in American English. Everything a resident or the evaluator reads — agent instructions, tool messages, API `detail` texts, the README — is in Brazilian Portuguese. Contract field names (`resposta`, `confirmacoes_pendentes`, ...) and tool names follow the PT-BR contract.

## Consequences
Domain names in code mix both languages where the contract imposes PT-BR (`reservar_area`, `apartamento`).
