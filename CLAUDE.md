# Claude Code Instructions

## Git

Always use `git commit -s` to include a `Signed-off-by` trailer.

Never push to remote. Only the human pushes — they need to review
what goes out. Prepare commits, but stop before `git push`.

## Formatting

Before committing, run `bazelisk run //:fix_lint` to format and lint all changed files. This is the single source of truth — do NOT run `buildifier`, `bazelisk mod tidy`, or `black` individually, as `fix_lint` handles all of them with the correct CI-compatible configuration:

- `buildifier` on changed `.bzl`/`BUILD`/`MODULE.bazel` files (respects `.bazelignore`)
- `bazelisk mod tidy` with CI config when `MODULE.bazel` changed (ensures lockfile matches CI)
- `black` on changed `.py` files

Just run:

```sh
bazelisk run //:fix_lint
```

CI config is applied automatically via `--bazelrc` flags — no `user.bazelrc` needed.
This also handles sub-module lockfiles (e.g. `gallery/MODULE.bazel.lock`).

## Gallery

`gallery/` is a separate Bazel workspace with its own `MODULE.bazel`.
It contains example ORFS designs that exercise bazel-orfs features.

- **bazelisk** commands for gallery targets require `cd gallery` first
- gallery uses `local_path_override(path = "..")` to reference bazel-orfs,
  so changes to bazel-orfs rules are immediately visible in gallery builds
- Gallery-specific skills are prefixed with `demo-` (e.g., `/demo-add`,
  `/demo-debug`, `/demo-update`)
- Gallery has its own `.bazelrc` and `user.bazelrc` (gitignored)

### Human-only external actions

Never run commands that create or modify external state. The human does
all of these manually:

- `gh pr create`, `gh issue create`, `gh pr merge`, `gh pr comment`
- `git push` (to any remote)
- Any GitHub API write (`gh api` with POST/PUT/PATCH/DELETE)

Prepare the content (branch, issue markdown, PR description) and stop.
The human reviews and publishes.
