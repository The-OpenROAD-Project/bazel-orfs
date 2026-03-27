# Gallery — Project Instructions

This is a separate Bazel workspace inside bazel-orfs. It contains example
ORFS designs that exercise bazel-orfs features and prototype new capabilities.

## Structure

- `gallery/MODULE.bazel` uses `local_path_override(path = "..")` to reference
  the parent bazel-orfs, so rule changes are immediately visible
- `gallery/` has its own `.bazelrc` and `user.bazelrc` (gitignored)
- Skills in `.claude/commands/` (at the bazel-orfs root) target gallery with
  the `demo-` prefix (e.g., `/demo-add`, `/demo-debug`, `/demo-update`)

## Building

```bash
cd gallery
bazelisk build //serv:serv_rf_top_synth
bazelisk test //smoketest:counter_synth_lint_compare
```

## Utility scripts

- `bin/git-read <dir> <subcmd>` — cross-repo git reads
- `bin/curl-read <https-url>` — read-only HTTPS fetch
