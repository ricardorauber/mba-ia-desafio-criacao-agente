# 0008 - Deliver without a real Gemini run

- Date: 2026-10-22
- Spec: 0008-readme-and-delivery
- Status: accepted

## Context
Spec 0008 AC3 asks for a real run of the evaluator flow against Gemini. No Google AI Studio key is available on this machine.

## Options considered
- A: Wait for the user to provide a key and run the flow — proves behavior with the real model, blocks the delivery.
- B: Deliver now, relying on the scripted-model test suite, an independent code review, and the evaluator script for a later real run — no proof against the real model's choices.

## Decision
The user chose B: "Vamos tentar entregar sem Gemini" ("Let's try to deliver without Gemini").

## Consequences
AC3 of spec 0008 stays unchecked. `scripts/fluxo_avaliador.py` is shipped so the flow can be run as soon as a key exists. The default model name was checked against the official model list instead (see spec 0009).
