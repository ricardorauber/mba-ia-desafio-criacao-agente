# 0008 - README, end-to-end run and delivery

## Goal
Replace the challenge statement with the delivery README and prove the whole evaluator flow (steps 1-15) against the real Gemini API.

## Scope
- In: `README.md` (sections Arquitetura, Garantias, Como rodar), `scripts/fluxo_avaliador.py` (runs steps 1-14 over HTTP and prints each check), model choice confirmed against the user's AI Studio project.
- Out: new behavior; any fix found here becomes a new spec.

## Requirements
- R1: `README.md` SHALL have the sections **Arquitetura** (each agent, its responsibility, how it is triggered and why), **Garantias** (for each of the five guarantees: file, function/excerpt and why it does not depend on the model) and **Como rodar** (prerequisites, `.env` variables, `uv sync`, restore command, start command), in PT-BR.
- R2: Every file and symbol cited in **Garantias** SHALL exist in the repository.
- R3: `scripts/fluxo_avaliador.py` SHALL run steps 2-14 of the evaluator flow against `http://localhost:8000` (step 13 restart is done by the operator between two invocations: `--ate-12` and `--depois-do-reinicio`) and print PASS/FAIL per check.
- R4: The default model in `.env.example` comment / spec 0004 SHALL be one that exists in the Gemini API at delivery time and fits the free-tier limits for a few dozen calls; if `gemini-3.5-flash` is not available, the default changes and ADR 0003 is updated.

## Acceptance criteria
- [ ] AC1: The README has the three sections and no leftover of the challenge statement. (R1)
- [ ] AC2: A script check confirms each path and symbol cited in **Garantias** exists. (R2)
- [ ] AC3: A real run of the flow (restore → API → steps 2-12 → restart → steps 13-14) prints only PASS. (R3, R4)
- [ ] AC4: `git ls-files` shows no `.env` and no key; `git diff be87e1d -- dados` is empty; `uv.lock` pins `google-adk==2.12.0`. (Delivery)

## Unit tests
- T1: `tests/test_readme.py::test_guarantee_references_exist` parses the backticked paths and `path::symbol` references of **Garantias** and checks they exist (AC2).
