# 0002 - Fast-forward main after each spec

- Date: 2026-10-22
- Spec: all
- Status: accepted

## Context
The delivery must be on `main` of the public fork, and the build flow works in one branch per spec.

## Decision
Each spec is built in its own worktree and branch; once green, committed and pushed, `main` is fast-forwarded to it and pushed, and the next spec branches from the updated `main`.

## Consequences
`main` always holds the last verified spec; history stays linear.
