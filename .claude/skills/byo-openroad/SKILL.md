---
name: byo-openroad
description: Iterate on local OpenROAD source changes against a bazel-orfs flow by building the OpenROAD checkout binary and injecting it via OPENROAD_EXE (a bring-your-own / BYO loop), instead of encoding the diff as a base64 patch swapped into the archive_override. Use when developing or debugging an OpenROAD C++/TCL change that you need to exercise through an ORFS stage (cts, place, grt, route), when a long edit-build-run loop is taxing turnaround, or when a change "isn't taking effect" and you suspect a silently-rejected patch.
---

## Goal

When you are changing OpenROAD source and need to see the effect through a
bazel-orfs flow stage, run the flow against a binary you built directly from
your OpenROAD checkout — **bring your own OpenROAD** — rather than routing the
change through the module-graph patch mechanism.

## The two mechanisms, and why BYO wins for a debug loop

There are two ways to get a local OpenROAD change into a flow run:

1. **Patch the archive_override** — encode your `git diff` (often base64) and
   splice it into the OpenROAD `archive_override` / `git_override` in
   `MODULE.bazel` so bazel applies it at fetch time with `patch -p1`.
2. **BYO** — build openroad straight from the checkout and hand the flow that
   binary via an `OPENROAD_EXE=` override.

The patch mechanism is the right thing for the **final, carried** change (it is
reproducible and hermetic). It is the wrong thing for an **iteration loop**:

- `patch -p1` **silently rejects hunks** on context drift. The build keeps
  going, and you end up debugging a binary that does not contain your change —
  the single most expensive failure mode, because nothing tells you.
- The regenerate-diff → re-encode → swap → re-fetch → rebuild cycle is applied
  on every fetch and taxes every iteration.

BYO removes both: the working tree **is** the source, so there is nothing to
re-encode and nothing to silently reject.

## The BYO loop

```bash
# 1. Build openroad from your checkout (the working tree is the source).
cd /path/to/OpenROAD          # your OpenROAD checkout / ORFS tools/OpenROAD
bazelisk build //:openroad    # (or the checkout's cmake build)

# 2. Point the flow / extracted stage harness at it.
export OPENROAD_EXE="$(readlink -f bazel-bin/openroad)"
# ... then run the ORFS stage (make do-<stage>, or an extracted _deps run).
```

The ODB is compatible across the two binaries as long as your checkout and the
flow's pinned OpenROAD share a base revision.

## Three-tier test loop — climb only as far as you must

Pick the cheapest tier that can reproduce what you are chasing; escalate only
when it cannot:

1. **Pure unit gtest (sub-second).** A dependency-free kernel test on the
   algorithm/math you changed. No STA, no ODB, no relink of the tool library.
   This catches most logic errors in milliseconds.
2. **In-checkout regression test (seconds).** OpenROAD ships `//src/<tool>/test:*`
   targets — real STA on a tiny design. These are maintained and need **no**
   `OPENROAD_EXE` plumbing, so for anything they cover, prefer them over BYO.
3. **Flow-level BYO run (minutes+).** The full ORFS stage on a real design with
   your BYO binary — the final confirm. BYO earns its setup cost only here, for
   loops the wired tests in tiers 1–2 cannot reach (e.g. a specific placed ODB).

## It is a judgement call, not a rule

Weigh BYO against just using the already-wired tests. Tiers 1–2 are maintained
and plumbing-free; use them whenever they cover the change. BYO is for the
long / flow-level loops they can't reach.

## The real fix: make a rejected patch LOUD

The root hazard is that `patch -p1` returns nonzero on a reject but the build
swallows it. Whatever your carry mechanism, make a mis-applied patch **fail the
build hard** rather than masquerade as a working binary:

- check the `patch` exit status and abort the build on nonzero, **or**
- add a post-patch sentinel: grep the patched file for a known unique line from
  your patch and fail if it is absent.

A loud patch failure turns the worst BYO-motivating failure mode (a silent
no-op binary) into an immediate, obvious build error — at which point the patch
path is safe for iteration too.
