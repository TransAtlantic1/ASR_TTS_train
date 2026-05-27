# Shared AGENTS Template

Use this file as the reusable baseline for project-level `AGENTS.md`.
Project-specific `AGENTS.md` files should keep only local deltas: repo
structure, domain constraints, build/test commands, path conventions, and
active operational context.

## Working Model

- The main agent owns user communication, planning, final acceptance, and
  cleanup.
- Keep short, local, low-risk tasks in the main agent so the task can move
  end-to-end without unnecessary handoffs.
- Prefer the smallest safe change. Do not widen scope without a clear reason.
- Review current worktree state before editing and avoid touching unrelated
  user changes.
- If a local rule conflicts with a shared rule, the local project rule wins.

## Subagent Rules

- Prefer fewer subagents. Keep work local unless delegation materially
  improves throughput, isolation, or review quality.
- Use subagents for long-horizon work: broad codebase or dataset exploration,
  long-running verification, heavyweight implementations with a clean write
  boundary, or adversarial review that benefits from an independent pass.
- Do not delegate short, tightly scoped tasks just to preserve a coordinator /
  worker split. Small reads, narrow edits, and quick checks should stay in the
  main agent.
- Keep blocking decisions and final acceptance in the main agent.
- Each subagent should own one complete, reviewable task chain rather than a
  thin partial step. The task should have a clear start, execution scope, and
  expected feedback.
- Give each subagent a bounded responsibility and a disjoint write scope.
- Do not let multiple subagents edit the same files or own the same decision.
- When a subagent is created, ensure `subagent.md` exists in the current
  working directory. Create it if missing; otherwise append to it.
- Record one entry per subagent in `subagent.md`. Each entry should include the
  address or reference needed to find that subagent's session record, the
  assigned task, and a brief completion summary or current status.
- When delegating, describe the full task chain in the prompt:
  goal, scope, inputs, files or surfaces owned, commands or checks to run,
  expected deliverable, and the exact reply format needed back.
- Require the subagent to return a complete handoff: what it changed or
  inspected, what it found, what checks it ran, concrete outputs or evidence,
  and any remaining risks or blockers.
- Reclaim every completed or failed subagent manually. Review its output before
  accepting or building on it.
- A review subagent may inspect the diff and tests, but the main agent still
  owns fix selection and final sign-off.
- Choose the subagent model by task difficulty. Use a cheaper bounded model
  such as `gpt-5.3-codex` for narrow implementation or inspection tasks, and
  reserve the newest model for ambiguous, high-risk, or harder reasoning work.

## Git Submission Rules

- Start by checking `git status --short`.
- Stage only files that belong to the current task.
- Use explicit `git add <path>` calls. Do not rely on broad staging patterns.
- Commit once the task is coherent. Use a short imperative subject, ideally
  scoped by subsystem or feature.
- Do not rewrite history, amend commits, or reset unrelated work unless the
  user explicitly asks for it.
- If a generated, local, or runtime-only file should stay untracked, add a
  rule to the nearest relevant `.gitignore` instead of leaving noise in the
  worktree.
- Treat `*.log`, `*.nohup.log`, `host.nohup.log`, `worker.*.nohup.log`,
  `core.*`, caches, and one-off runtime outputs as ignore-by-default noise
  unless the project explicitly tracks them.
- Before handoff, record the checks you ran and any important commands or
  metrics.

## Adversarial Review

- Run one adversarial review after any non-trivial implementation.
- A dedicated review subagent is allowed and preferred when the task is large
  enough to benefit from a second pass.
- The review should assume the change is wrong and try to prove it by finding
  bugs, regressions, broken assumptions, missing tests, doc drift, naming
  drift, ignore leaks, or over-broad edits.
- Findings come first. Summaries come second.
- High-severity findings should be fixed before handoff unless the user wants
  a review-only outcome.
- Store reusable review prompts under `prompts/review/`.

## Project Deltas

When deriving a repo-specific `AGENTS.md`, add:

- repository layout and ownership boundaries
- build, test, lint, and release commands
- storage and artifact placement rules
- repo-specific safety constraints
- active migrations, cutovers, or temporary operational notes
