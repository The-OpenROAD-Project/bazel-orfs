> **Repo**: Run from the openroad-demo root. `git diff` and `bazelisk` target this repo.

Re-test all affected demo projects and update the Projects table.

CI runs `bazelisk test ...` on every PR and push to main, but only covers
projects with test targets. Use this skill before merging to verify nothing
regressed in projects not yet covered by CI.

## 1. Determine affected projects

Check `git diff` against the base branch to find what changed:

- If `defs.bzl`, `MODULE.bazel`, or `scripts/` changed → **all projects** are affected
- If only `<project>/` files changed → only that project is affected
- If `requirements_lock.txt` changed → projects using Python generators are affected

List all project directories using Glob to find `*/BUILD.bazel` patterns.

## 2. Build each affected project

For each affected project, use `/demo-debug <project>` to build incrementally
through all stages. Trust the bazel cache — unchanged projects will be instant.

## 3. Extract metrics and update the table

For each rebuilt project, extract metrics (cells, area, frequency, WNS) from
the build reports and update:

- The project's `README.md` results table
- The top-level `README.md` Projects table row

Get the current ORFS image hash from `MODULE.bazel` and update the "Built with"
column with the short hash (first 7 chars of the git hash from the image tag).

## 4. Generate gallery screenshots

For each affected project, build the gallery image:
```bash
bazelisk build //<project>:<top_module>_gallery
```

## 5. Update build times

For each affected project, update build times and regenerate the chart:
```bash
bazelisk run //scripts:build_times -- <project>
```

After all projects are updated:
```bash
bazelisk run //scripts:build_time_chart
```

## 6. Self-review

Run `/demo-review` to check all changes for style and policy consistency before summarizing.

## 7. Summarize results

Report:
- Which projects were rebuilt vs. cached
- Any regressions (frequency dropped, new timing violations, build failures)
- Updated metrics for each project

If there are regressions, flag them clearly and suggest fixes.

ARGUMENTS: $ARGUMENTS
