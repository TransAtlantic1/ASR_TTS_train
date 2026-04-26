$planning-with-files

This is a bug investigation and fix task in the `icefall` repository. Follow the planning-with-files workflow before changing code.

1. Check or create `task_plan.md`, `findings.md`, and `progress.md` in the current working directory.
2. Reproduce the bug or collect the exact failing symptoms first.
3. Identify the smallest relevant scope in `icefall/`, `egs/...`, `test/`, and `docs/`.
4. Record the bug statement, reproduction steps, expected behavior, actual behavior, and suspected root causes in `findings.md`.
5. Write a phased plan in `task_plan.md` covering reproduction, root-cause analysis, fix, regression checks, and documentation updates if needed.
6. Log every failed attempt, error message, and changed hypothesis in `progress.md` and `task_plan.md`.
7. Do not jump to a fix until the likely root cause is supported by code evidence.
8. Implement the smallest correct fix.
9. Add or update the most relevant tests.
10. Run the smallest meaningful verification commands first, then broader checks if needed.
11. Before finishing, summarize the root cause, changed files, and verification results in `progress.md`.

Bug to investigate:
<replace this with the actual bug, error, or failing behavior>
