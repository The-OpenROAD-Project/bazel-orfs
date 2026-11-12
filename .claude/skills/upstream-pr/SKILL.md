---
name: upstream-pr
description: >-
  Turn fixes carried in bazel-orfs as patches into an upstream pull request (OpenROAD, ORFS,
  ...) that a maintainer can review: one commit per concern written for the upstream reader,
  linted with upstream's own tools (OpenROAD's Bazel //:fix_lint and clang-tidy aspect, never
  a host clang-format, clang-tidy, tclint or black), a draft force-pushed only until it is
  ready, every review-bot comment verified, answered and resolved, the carried patch left as
  it is while the pull request settles. Only once the human has ordered that upstream pull
  request. Also before every push to one, and when its lint or clang-tidy check fails.
---

> **Repo**: Run from the bazel-orfs root, with a clone of the upstream repository (OpenROAD, ORFS, ...) in `tmp/`. Applies only once the human has ordered the upstream pull request; until then the change is a carried patch (CLAUDE.md, "Upstream repositories").

How a fix carried here as patches becomes an upstream pull request a maintainer can review. Which carried patches are candidates at all, and whether a bump or a deletion sheds one first, is the `carried-patches` skill. The carried patches churned where churn was cheap; the pull request is the settled change, told to someone who has never seen bazel-orfs.

ARGUMENTS: $ARGUMENTS

## 1. One commit per concern

A carried series records the order things were found in: a feature, a fix to it, a lint fix, another fix. The pull request records the concerns: one commit each, each building and passing its own tests, in an order where each one only adds.

Build the series from snapshots rather than by rebasing the history: on a fresh branch off upstream's tip, for each concern, check out the final state of the files that concern owns (`git checkout <final> -- <paths>`, or an edit of a shared file down to that concern's part) and commit. The last commit's tree must equal the final tree; `git diff <final> HEAD` empty is the check. Then run each commit's own tests at that commit.

Ordered by the human as one pull request per concern, the series is split across pull requests; a pull request that needs another's unmerged change says so and stays a draft (`dogfooding`, rule 6).

## 2. Written for the upstream reader

Commit messages and the pull request body say what the change does and why, in upstream's terms. Scrub the bazel-orfs bookkeeping: carried patch numbers, "carried", ladder rows, our branch names, the order things were found in. One link to the bazel-orfs pull request that is the integration test is enough context.

The body leads with the number: what the change buys, measured, in a table if there are several designs. Then one line per commit. Then what the tests check.

The tests check intended behaviour, not golden output (`dogfooding`, rule 5); a new `.ok` or `.defok` is a review comment waiting to happen.

## 3. Upstream's lint, with upstream's own tools

Lint with the tools upstream wires up, never with the ones installed here. A host `clang-format`, `clang-tidy`, `tclint` or `black` is another version with another configuration: it reformats lines the change never touched, or passes what CI flags. Each finding CI catches instead is a round trip through a job that takes tens of minutes, and a papercut commit on a pull request under review.

OpenROAD wires its linters into Bazel at CI's pins (`docs/contrib/LintTargets.md`, `AGENTS.md`); use those and nothing else:

- `bazelisk run //:fix_lint` does everything: formats, then lints, C++, Tcl, Starlark, Python and YAML. `bazelisk test //:lint_test` checks without writing.
- One language at a time: `//:tidy_cc` (clang-format, not clang-tidy), `//:tidy_tcl`, `//:tidy_bzl`, `//:tidy_py` and `//:tidy_yaml` format in place; `//:fmt_<lang>_test` and `//:lint_<lang>_test` check. The full list is `docs/contrib/LintTargets.md`.
- clang-tidy is not in `fix_lint`. It runs as a Bazel aspect with the LLVM toolchain's clang-tidy, as CI's Clang-Tidy-Bazel job does: `bazelisk build --config=lint //src/<module>/...` for each module the change touches, then `tools/lint/collect_clang_tidy.sh "$(bazelisk info bazel-bin)" tidy.txt` for the findings; the build alone prints none. CI fails only on findings on lines the pull request changes. Fix those and leave the rest: a module has hundreds of findings on lines nobody touched.
- Under remote execution the clang-tidy actions can fail with `'stddef.h' file not found`, and the collector then counts only the files that ran. Add `--strategy=AspectRulesLintClangTidy=local`, and read the collector's `clang-tidy outputs` count before trusting `Findings: 0`.
- Lint the branch merged with upstream's master, in a local throwaway merge that is never pushed. CI lints that merge, and the lint configuration changes on master too: a branch based before OpenROAD's bfa8233b0c (2026-11-11) cannot run clang-tidy at all on its own.

Where upstream has not wired a linter into Bazel, ORFS today, read the version from upstream's CI configuration (`.github/workflows/black.yaml`; tclint and tclfmt in `.github/requirements/requirements_lock.txt`) and install exactly that version in a venv under `tmp/`. Do not copy the versions into this skill; they go stale.

Generated files equal their generator's output. ORFS's variable documentation is generated from `variables.yaml`; run the generator, and when it also rewrites drift unrelated to the change, put only the change's part in by hand so the diff stays the change's.

Lint every commit, not only the last: a series where commit 2 fixes commit 1's lint is two concerns, one of them noise.

## 4. Draft first, and force-push only while it is a draft

Open the pull request as a draft. Correctness evidence that takes hours can come after it is opened; it may fail, and a draft says that is possible.

While it is a draft, rewrite freely and force-push: squash, reorder, fix commits in place, so the series stays one commit per concern. Once the human marks it ready for review, stop: new commits only, fast-forward pushes, so a reviewer's comments stay attached to what they read.

## 5. Bot review: verify, answer, resolve

Every review-bot comment is verified, answered and resolved, as
`docs/agent-rules.md` ("Review bots: trust, but verify") says; a nit that
is taken goes into the commit that owns the concern.

## 6. The carried patch stays put while the pull request settles

Review changes the pull request: a bot's nit, a maintainer's question, a rename. Do not mirror each round into the carried patch. An edit to a file in `patches/` changes the key of every stage that takes the patched tree, so it costs every consumer a rebuild (`cache-miss`), and the patch retires anyway at the `//:bump` onto the merged pull request, which brings whatever review settled on. Until that bump, the patch keeps what it carried and its header points at the pull request.

Update it before then only for an urgent need: the carried version breaks a build here or gives a wrong result, and waiting for the merge costs more than the churn. That update is a fix in its own right, with the reason in the patch header, not a sync with the review.
