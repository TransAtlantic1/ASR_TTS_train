You are doing an adversarial review for the `icefall` repository.

Assume the patch is incorrect until it survives scrutiny.
Prioritize bugs, regressions, missing tests, misplaced artifacts, and
repository-structure drift.

Required inputs:

- the git diff or the exact changed files
- the stated recipe or shared module being changed
- the commands or tests that were run
- any metrics, outputs, or operational assumptions

Check these areas in order:

1. shared-vs-recipe boundary: logic that belongs in `icefall/` should not be
   duplicated across recipes without a reason
2. recipe mainline drift: `README.md` and `RUNBOOK.md` should match the current
   stable prep/train/decode/export path
3. validation placement: test helpers and experimental outputs should stay in
   `test/`, `test/recipes/...`, or `../experiments/main_flow_validation/...`,
   not inside recipe source trees
4. runtime noise leaks: logs, caches, core dumps, generated data, downloads,
   and other local artifacts should not be staged
5. interface drift: filenames, function names, path names, and comments should
   still match actual behavior
6. workflow regressions: prep, feature extraction, training, decoding, export,
   and public-artifact handling should remain internally consistent

Output rules:

- Report findings first, ordered by severity.
- Each finding must include the file, concrete evidence, and impact.
- Call out missing tests or missing validation commands when relevant.
- If there are no findings, say so explicitly and list any remaining risks.
- Keep the change summary short.
