---
name: cache-miss
description: >-
  Ask whether a target is a remote cache hit on this machine without building it: a capture
  kills every miss as it appears and lists the actions behind it as not reached, minutes on
  a laptop. When another machine built it, compare tree hashes first, then the two machines'
  miss lists. Trust the cache and never clean it; to rebuild an artifact, poison the cache:
  a code change that reaches its key (a comment may be canonicalized away). Use before building any long flow target,
  when XSTile_grt or any stage rebuilds unexpectedly, before cleaning or deleting any cache,
  or before blaming Scala, a toolchain or the cache.
---

> **Repo**: Run from the bazel-orfs root. Applies to any target, and was written for `//test/coremark_joule/designs/asap7/xiangshan:XSTile_grt`, whose cold build is six hours.

*Is this target a remote cache hit here?* is a capture that never executes an action, minutes on any machine, a laptop included. Never commit an execution log.

ARGUMENTS: $ARGUMENTS

## Check the cheap explanation first

**Is the other machine on the same tree?** Every ORFS stage action, synthesis included, takes the whole patched ORFS `flow/scripts` tree as input: the synthesis canonicalize action's inputs include `global_place.tcl`, `global_route.tcl`, `detail_place.tcl` and `variables.yaml`. So one carried patch in `patches/` for global placement changes the key of every stage from synthesis on, and a patch to OpenROAD itself changes the `openroad` binary, which every stage also takes as input. A day with a batch of carried patches is a day nothing built before it is reusable. `git rev-parse HEAD^{tree}` on both machines settles most cases; `git log -1` does not, because a commit hash dies in a rebase and the tree hash does not.

## Trust the cache; never clean it

Bazel's caches are keyed on content: what they serve is the result of those inputs. Never clean them: not `bazel clean` (the guard blocks it), not `--expunge`, not deleting the disk cache, the output base or a `bazel-*` tree. A rebuild you did not expect is a key that changed, and this skill finds which.

When an artifact has to be rebuilt anyway (a cached result that is wrong, or stale), poison the cache: change code so that the artifact's key changes. The change has to reach the key of the action that builds the artifact. A comment can be canonicalized away before it gets there: synthesis canonicalizes the RTL first, so a Verilog comment re-runs the canonicalize action and can leave its output, and with it every stage after, byte-identical and cached. Change something the building action itself reads, and confirm with this skill that the target now misses. The change re-keys the artifact on every machine and in CI; a clean would rebuild it on one.

## What is already known to be hermetic

Measured, so you do not measure it again unless something changed:

- **The Chisel to FIRRTL chain.** `//test/coremark_joule/xiangshan:xiangshan_fir` from a brand-new output base, reading the remote cache only: all 951 spawns (Scalac, Javac, espresso's C, protobuf, the fir genrule) were remote hits, so the fetched Maven jars, XiangShan archives, Scala toolchain and firtool are byte-identical from one fetch to the next. The generator runs on `remotejdk11`, not the host JDK.
- **C++ tools.** yosys, abc, make and OpenROAD build with the hermetic `@llvm` toolchain, so the host gcc does not matter.
- **Action environments.** `--incompatible_strict_action_env`: `PATH=/bin:/usr/bin:/usr/local/bin`, `PWD=/proc/self/cwd`, no home paths in any command line.
- **One host input, harmless today.** `@ncurses//:local_terminfo` is a symlink to the host's `/usr/share/terminfo`, an input of `@ncurses//:fallback_c`. That genrule's key differs between distros, but ncurses is built with no fallback terminals, so `fallback.c` is the same stub everywhere and nothing downstream moves. On a distro nobody built on before, that genrule is the one `ran` a capture reports: it finishes before it can be killed and its output is the same stub.

## Is it cached?

```sh
bazelisk run //tools/cache_evidence -- capture \
  //test/coremark_joule/designs/asap7/xiangshan:XSTile_cts
```

Prints the counts, every miss, every action left unreached behind one, or `every action is a remote cache hit`. Exit status 1 means a miss or an unreached action; 0 means neither (an action listed as `ran` is not a hit, and does not fail the exit status). Minutes: a repository fetch, an analysis, one cache lookup per action.

`capture` never executes an action, and three choices make that true; each exists because the obvious alternative was tried and failed:

- **A fresh output base** (under `./tmp/cache_evidence/`, deleted afterwards). Bazel logs no spawn that was a local action-cache hit, so on the machine that built the target an ordinary run logs nothing at all.
- **A miss is killed the moment it appears.** Every action is spawned sandboxed, and a thread kills whatever process appears under the output base's sandbox directory, so a miss fails in a blink, logged with its inputs, and `--keep_going` carries the build to every other action whose inputs exist. Remote hits never spawn a process; the strategy is not part of any key. This replaced blocking `/usr` and `/bin` in linux-sandbox, which Ubuntu's AppArmor denies unprivileged users, and interrupting the client, which left the server computing the miss for as long as the stage takes. `--experimental_remote_require_cached` fails an action only after it has run, and `--spawn_strategy=remote` with no executor fails every action before the cache is asked, so neither helps. An action so short it finished before it could be killed is logged as `ran`: not a hit, and not uploaded.
- **Actions behind a miss are listed, not omitted.** Their inputs were never produced, so Bazel cannot key them. `capture` asks `aquery` for the in-scope actions and lists every one the log lacks as `not_reached`. Without this an XSTile stage that was never keyed looked no different from one that was never in the graph.

## When another machine built it

Compare the tree hashes first, then `bazelisk version` and the options
`--announce_rc` prints: a different tree is the answer on most days.
With those equal, run
`capture` on both and compare the miss lists; the first action that
misses on one side and hits on the other is where the keys part, and
`--keep` leaves its execution log (`exec.log.zst`) under
`./tmp/cache_evidence/` to inspect.

No evidence is committed next to a design any more. The files were
meant to be recaptured by every pull request that moved a design's keys,
which in practice nobody did: within three weeks they described a tree
nothing was at.
