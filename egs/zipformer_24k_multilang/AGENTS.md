# Project Agent Rules

## Highest Rule: Ask When Uncertain

- If the goal, expected behavior, data source, ownership boundary, risk level,
  or acceptance criteria is unclear, stop and ask the user before deciding.
- Do not silently choose between materially different plans, product behavior,
  interfaces, dependencies, data handling rules, or destructive operations.
- When asking, state the concrete uncertainty, the available options, and the
  default you would otherwise choose.
- Local rules, tool output, and prior context do not override a direct user
  answer for the current task.

## Git Tracking And Submission

- Start every task by checking `git status --short`.
- Treat existing modified, deleted, or untracked files as user work unless they
  clearly belong to the current task.
- Keep edits scoped to the requested task. Do not reformat, rename, delete, or
  reorganize unrelated files.
- Stage only task-owned files with explicit `git add <path>` commands.
- Do not use broad staging patterns such as `git add .` or `git add -A`.
- Do not rewrite history, amend commits, reset work, or discard changes unless
  the user explicitly asks.
- If a commit is requested, commit only after the task is coherent and checks
  have been run or consciously skipped. Use a short imperative subject.
- If generated, local, or runtime-only files appear, add a rule to the nearest
  relevant `.gitignore` instead of leaving avoidable worktree noise.
- Treat `*.log`, `*.nohup.log`, `host.nohup.log`, `worker.*.nohup.log`,
  `core.*`, caches, notebook checkpoints, and one-off runtime outputs as
  ignore-by-default unless the project explicitly tracks them.
- Before handoff, report the files changed, checks run, and any important
  commands, metrics, skipped checks, or remaining risks.

## Long Task Planning

- For long-running, multi-step, research-heavy, or ambiguous tasks, use the
  `planning-with-files` skill automatically before execution.
- See `skill/planning.md` for the local usage note.
- Treat tasks that are likely to require 5 or more tool calls, multiple phases,
  session recovery, or substantial discovery as long tasks.
- Create and maintain `task_plan.md`, `findings.md`, and `progress.md` in the
  project root according to the skill workflow.
- Re-read the plan before major decisions, update progress after each phase,
  and log errors or failed attempts so the same failure is not repeated.
- If it is unclear whether a task should use the planning workflow, ask the
  user before deciding.

## Matt Pocock Skills

- Use `mattpocock/skills` when the user names it or the task clearly matches
  its workflow. See `skill/matt-pocock-skills.md`.
- Only trigger these skills for long-running, complex, ambiguous, or multi-step
  tasks. Do not trigger them for small module edits, narrow fixes, or simple
  single-file changes.
- Trigger it for grilling requirements or designs, TDD, bug diagnosis,
  PRD/issue/triage work, architecture review, zooming out for context, or
  creating and improving skills.
- During planning, use a subagent with `grill-me` or `grill-with-docs` to
  challenge unclear requirements, plans, or designs before implementation.
- During test design, test-first implementation, regression testing, or bug-fix
  verification, trigger `tdd`.
- When commands, tests, runtime behavior, or performance fail unexpectedly,
  trigger `diagnose`.
- During refactoring, codebase initialization, or unfamiliar codebase/module
  exploration, trigger `improve-codebase-architecture` or `zoom-out`.
- When managing project work through Git, GitHub, GitLab, issues, PRDs, or
  task triage, trigger `to-prd`, `to-issues`, `triage`, or
  `setup-matt-pocock-skills`.

## Automatic Adversarial Review

- For any non-trivial plan, start an adversarial review subagent before
  implementation. Ask it to challenge the plan, assumptions, scope, and
  acceptance criteria using `prompts/review/adversarial-review.md`.
- For any non-trivial implementation, start an adversarial review subagent
  before handoff. Ask it to inspect the diff, changed behavior, tests, docs,
  generated artifacts, and git state using
  `prompts/review/adversarial-review.md`.
- The review subagent should look for concrete failure modes first: correctness
  bugs, regressions, missing tests, unclear requirements, over-broad edits,
  naming drift, documentation drift, and leaked local artifacts.
- Findings must come before summaries and must include severity, location,
  evidence, impact, and a concrete recommended action.
- High-severity findings must be fixed before handoff unless the user requests
  a review-only outcome or decides otherwise.
- The main agent owns final decisions, user communication, and sign-off. If a
  review result creates uncertainty, ask the user instead of resolving it
  silently.
- If a subagent cannot be started, run the same adversarial prompt locally and
  state that fallback in the handoff.
