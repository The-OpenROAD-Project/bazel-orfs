---
name: analyze-before-push
description: >-
  Before every push to a pull request branch, run `bazelisk build --nobuild //...` (loading and
  analysis of every target, no actions, minutes) and push only when it passes. An analysis error
  stops every target in CI at once, and a pull request may be merged before a slower local check
  finishes. Use before opening or updating any pull request, after any bump (bazel-orfs, ORFS,
  OpenROAD, a BCR module), and after renaming or removing a variable, label, macro argument or
  visibility.
---

> **Repo**: Applies to bazel-orfs and to every workspace that consumes it, on every pull request.

Run analysis over the whole workspace before every push to a pull request branch, and push only when it passes:

```sh
bazelisk build --nobuild --keep_going //...
```

`--nobuild` loads every package and analyses every target, and runs no actions: no synthesis, no OpenROAD, no tests. On a warm server it takes seconds to minutes. `--keep_going` lists every error in one run instead of stopping at the first.

ARGUMENTS: $ARGUMENTS

## Why

An analysis error is not one failing target: Bazel refuses the whole build, and CI reports nothing else. It is also the cheapest failure to catch, and a pull request does not wait for a slower check. A bump PR, bazel-orfs #1379, was merged within minutes while its local test run was still building. The ORFS it bumped to had removed `REMOVE_ABC_BUFFERS` (ORFS#4580), and the stage variable check in `orfs_flow` refuses an unknown variable, so every package that set it failed at analysis on main. `--nobuild //...` names that error in a minute; the fix (#1380) needed a second PR.

## What it catches, and what it does not

Caught, because each is an error at loading or analysis:

- an ORFS variable a bump removed or renamed (the stage variable check in `orfs_flow`), or a misspelled one;
- a label to a file or target that moved or was deleted, such as a retired patch still listed;
- a visibility a change narrowed;
- a `select()` with no matching condition, a macro called with an argument it no longer takes, a `fail()` in a `.bzl`;
- a `MODULE.bazel` that does not resolve (an override on a module that left the graph, a missing repository).

Not caught: anything an action decides, such as a patch that no longer applies to a source archive fetched only for a build, a compile error, a failing test or a changed QoR number. CI and the targeted tests cover those. A patch is checked when the bump runs `bazelisk mod tidy` and when the repository is first fetched.

`//...` skips targets tagged `manual`. Name each manual target the change touches on the same command line.

## How

1. Run it in the worktree the branch is pushed from, at the commit that is pushed. Run it again after a rebase.
2. For a bump, first diff the new ORFS's `flow/scripts/variables.yaml` against the old one. Every removed or renamed name that a flow here sets must change in the same pull request.
3. When it fails, fix the cause in this pull request when the change caused it. When the failure is already on `main`, say so in the pull request body and fix it in a pull request of its own.
4. Say in the pull request body that `bazelisk build --nobuild //...` passes.
