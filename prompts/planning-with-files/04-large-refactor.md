$planning-with-files

This is a large refactor task in the `icefall` repository. Do not start implementation until the refactor plan is written down.

1. Check or create `task_plan.md`, `findings.md`, and `progress.md` in the current working directory.
2. Inspect the current architecture and identify the full impact surface across `icefall/`, `egs/...`, `test/`, `docs/`, scripts, and config-like files.
3. Record the current structure, pain points, invariants, interfaces, and migration risks in `findings.md`.
4. Write a phased refactor plan in `task_plan.md` with explicit boundaries, intermediate-safe states, verification steps, and rollback considerations.
5. Separate shared-library refactors from recipe-specific refactors unless there is a strong reason to couple them.
6. Prefer incremental changes that keep the repository runnable and testable after each phase.
7. After every phase, update `task_plan.md` and `progress.md` with what changed, what remains, and any newly discovered risks.
8. If the refactor changes behavior, interfaces, file locations, or commands, update tests and docs in the same phase.
9. Before finishing, verify the final structure and record the validation commands and outcomes in `progress.md`.

Refactor goal:
<replace this with the actual refactor objective>
