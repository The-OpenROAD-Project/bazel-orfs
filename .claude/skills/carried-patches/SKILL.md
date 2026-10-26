---
name: carried-patches
description: >-
  Shed patches carried on OpenROAD, ORFS, yosys or a BCR module, cheapest way first: drop a
  patch nothing uses, retire one a bump already carries (check_carried_patches says
  ABSORBED), and report the rest as upstream candidates, sorted into bugfixes and new topics,
  for the human to order. Every carried patch ends in one recorded state. Use when taking
  stock of patches/ or an override's patches and patch_cmds, after a bump, when a patch
  stops applying, or when asked which carried patches could go upstream.
---

Every carried patch is friction on every bump, but the ways to shed one cost very different amounts. In order, cheapest first:

1. **Drop it**: nothing uses it any more. A pull request here.
2. **Bump**: upstream already carries it. A pull request here, and no maintainer's attention spent.
3. **Upstream it**: a pull request upstream, and the maintainers' attention it costs. The human orders it (CLAUDE.md, "Upstream repositories"); the `upstream-pr` skill does it.

Go down a rung only when the one above it cannot shed the patch.

## 0. Is the patch still used?

A patch that applies is not a patch that is used. Before spending anything on one, find what consumes it:

- A patch that adds a knob (a new variable, option or Tcl argument) is dead when nothing sets the knob. Search the flows, designs and tests for it; a mention in a comment does not count.
- A dependency can be dead while BUILD files still name it: check that the source naming it is itself built. A test file outside the glob that generates the targets is never compiled, and so is every dependency it justified.
- A diagnostic patch whose investigation has ended is dead though its code still runs.

A dead patch is deleted in a pull request here, never sent upstream. Git keeps it.

## 1. Does a bump carry it?

`check_carried_patches` checks each patch against an unpatched tree: `CLEAN`, `ABSORBED` (upstream took it: delete the carry), `AMBIGUOUS` (its context occurs twice, so `ctx.patch` may apply it in the wrong place: widen the context) or `NEEDS_REBASE`. It reads the patches from `MODULE.bazel`, including those inlined into `patch_cmds` as base64, and checks a series in order, each patch against what the ones before it leave:

```sh
bazelisk run @bazel-orfs//tools/carried_patches:check_carried_patches -- \
    --tree openroad=$PWD/tmp/openroad
```

An ORFS series is a list in a `.bzl` (`ORFS_PATCHES` in `orfs_source.bzl`): give it with `--patch`, one per patch, in the order the list applies them.

Run it against the tree a bump would move to, not only the pinned one. `ABSORBED` there means the bump retires the patch; `NEEDS_REBASE` means the bump needs the patch rebased first.

What else retires a patch without an upstream pull request:

- A BCR module's newer `.bcr.N` revision fixes the overlay, dependencies or checksums without changing the upstream source, and is often exactly the carried fix: read `https://bcr.bazel.build/modules/<m>/metadata.json` for the versions and the candidate's `source.json`.
- A dependency may already pull a newer version through version selection: `bazelisk mod explain <m>` shows who asks for what. An override that a dependency's own `bazel_dep` makes redundant is deleted; no override at all is the best one.
- A dependency pinned to a commit: read upstream's log since the pin. The fix may be there, word for word.

One pull request per bump, so a regression bisects to one dependency. In the same pull request, delete the patch file and its entry.

A consumer that copies bazel-orfs's override patches into its own root (`docs/agent-rules.md`, "Bumping") runs the same check over its copies after each bump: a copy bazel-orfs has since dropped shows up as `ABSORBED`.

## 2. Report the rest, sorted

What survives the first two rungs is an upstream candidate. Report it to the human; do not act on it. Sort each one:

- **Bugfix**: a correctness fix any user of the dependency would want, settled by its churn here, with no design to discuss. Cheap for a reviewer; it can go as soon as the human orders it.
- **New topic**: a new option, a behaviour change, anything a maintainer must think about. It costs scarce attention: keep only a few open with the same maintainers at a time, and the next waits until one closes. A pull request against an issue already open upstream is not a new topic, but one that adds a feature still waits its turn.
- **Held**: tied to a conversation not yet had, or to an experiment not yet adopted. It stays carried whatever the queue, with the event that releases it.

## Record the state

Every carried patch ends in exactly one state, written in its header: what it fixes and how it retires (the `//:bump` onto an upstream that carries it), and then one of: the upstream pull request, once one exists; "held until <event>"; or the candidate's sort from rung 2. A dead or absorbed patch is deleted, not recorded. A later session reads the header instead of working the patch out again.
