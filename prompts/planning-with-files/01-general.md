$planning-with-files

This is a multi-step development task in the `icefall` repository. Do not start editing code immediately. Follow the planning-with-files workflow first.

1. Check whether `task_plan.md`, `findings.md`, and `progress.md` already exist in the current working directory.
2. If they do not exist, initialize them in the current working directory.
3. Read the relevant code, scripts, docs, and tests before changing anything.
4. Identify whether the work belongs in shared code under `icefall/`, recipe-specific code under `egs/<dataset>/<task>/...`, tests under `test/`, or docs under `docs/`.
5. Write an execution plan into `task_plan.md` with phases, risks, affected paths, and verification steps.
6. Write codebase findings, assumptions, and relevant file references into `findings.md`.
7. Write the current session actions and decisions into `progress.md`.
8. Only after the plan and findings are in place, start implementation.
9. After each completed phase, update `task_plan.md` and `progress.md`.
10. If a failure, test regression, or design change happens, record it in the planning files before continuing.
11. Before finishing, verify the changed behavior and record the commands and results in `progress.md`.

Current task:
<replace this with the actual icefall task>
