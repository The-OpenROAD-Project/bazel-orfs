> **Repo**: Run from the bazel-orfs root. Applies to any target, and was written for `//test/coremark_joule/designs/asap7/xiangshan:XSCore_grt`, whose cold build is six hours.

Find out why a target is not a remote cache hit on this machine when another machine built it, or why it rebuilds here when nothing seemed to change. Collect a few kilobytes of key evidence on each machine, commit them next to the design, and diff them. Never commit an execution log.

ARGUMENTS: $ARGUMENTS

## Check the cheap explanation first

**Is the other machine on the same commit?** Every ORFS stage action, synthesis included, takes the whole patched ORFS `flow/scripts` tree as input: the synthesis canonicalize action's inputs include `global_place.tcl`, `global_route.tcl`, `detail_place.tcl` and `variables.yaml`. So one carried patch in `patches/` for global placement changes the key of every stage from synthesis on, and a patch to OpenROAD itself changes the `openroad` binary, which every stage also takes as input. A day with a batch of carried patches is a day nothing built before it is reusable. `git log -1` on both machines settles most cases.

## What is already known to be hermetic

Measured, so you do not measure it again unless something changed:

- **The Chisel to FIRRTL chain.** `//test/coremark_joule/xiangshan:xiangshan_fir` from a brand-new output base, reading the remote cache only: all 951 spawns (Scalac, Javac, espresso's C, protobuf, the fir genrule) were remote hits, so the fetched Maven jars, XiangShan archives, Scala toolchain and firtool are byte-identical from one fetch to the next. The generator runs on `remotejdk11`, not the host JDK.
- **C++ tools.** yosys, abc, make and OpenROAD build with the hermetic `@llvm` toolchain, so the host gcc does not matter.
- **Action environments.** `--incompatible_strict_action_env`: `PATH=/bin:/usr/bin:/usr/local/bin`, `PWD=/proc/self/cwd`, no home paths in any command line.
- **One host input, harmless today.** `@ncurses//:local_terminfo` is a symlink to the host's `/usr/share/terminfo`, an input of `@ncurses//:fallback_c`. That genrule's key differs between distros, but ncurses is built with no fallback terminals, so `fallback.c` is the same stub everywhere and nothing downstream moves. The evidence witnesses it anyway (the `terminfo` line).

## Collecting the evidence

On each machine, from a checkout at the commit you are comparing:

```sh
bazelisk run //tools/cache_evidence -- capture \
  //test/coremark_joule/designs/asap7/xiangshan:XSCore_grt \
  --out test/coremark_joule/designs/asap7/xiangshan/cache_evidence/<machine>.txt
```

Name the file for the role, not the host (`machine_a`, `builder`, `laptop`): a hostname does not belong in a public repository. Then diff:

```sh
bazelisk run //tools/cache_evidence -- diff \
  $PWD/test/coremark_joule/designs/asap7/xiangshan/cache_evidence/machine_a.txt \
  $PWD/test/coremark_joule/designs/asap7/xiangshan/cache_evidence/machine_b.txt
```

`capture` costs a repository fetch and an analysis, a few minutes, not a build. Three choices make that possible, and each exists because the obvious alternative was tried and failed:

- **A fresh output base** (under `./tmp/cache_evidence/`, deleted afterwards). Bazel logs no spawn that was a local action-cache hit, so on the machine that built the target an ordinary run logs nothing at all.
- **A miss fails at once instead of running.** `--experimental_remote_require_cached` does not do this with a remote cache and no remote executor: the build synthesised locally. Instead the sandbox blocks `/usr` and `/bin`, so an action the cache does not have fails in a second, logged with its key and inputs, and `--keep_going` collects every such action at the frontier. Remote hits never execute, and sandbox options are not part of any key. `--allow_local` lets the misses run and interrupts the build at the first one instead.
- **Only key evidence is kept.** The compact execution log of the XSCore_grt graph is 5 MB compressed and 90 MB raw; the evidence is about 25 KB.

## Reading the evidence and the diff

An evidence file has, in order:

- `target`, `bazel`, `commit ... dirty`, `host` (distro, libc, architecture), `terminfo`;
- `option` lines: what `--announce_rc` reports. Values of options that name private infrastructure (remote cache, headers, credentials) and home paths are hashed as `<sha:...>`, so two machines can still be compared without the hosts appearing;
- `spawns N hit H ran R miss M` for the whole graph;
- `tool <digest> <files> <group>`: each tool the in-scope actions run (the openroad and yosys binaries, yosys's share directory, the python wrapper's runfiles tree, make, klayout's mock);
- `spawn <key> <hit|ran|miss> <mnemonic> <first output> args= env= tools= sources= design=`: every action under `--scope` (default `//test/`), with its remote cache key and separate digests of its arguments, environment, tools, external sources and design inputs.

`diff` prints what differs, most fundamental first, and ends with the first differing action:

- `bazel:`, `commit:` or `option only in ...`: a different Bazel, tree or flag set. Every key can move; fix that before reading further.
- `tool <group>`: a tool binary differs. If the commits match, that tool's build is not reproducible across the machines; rerun `capture` with `--scope` set to the tool's repository (`@@openroad+//`, for instance) to itemise its build.
- The first differing `spawn`, and the part that moved: `sources` means the patched ORFS tree or a PDK file differs (a carried patch, a bump); `design` means an upstream action produced different bytes, so look at the spawn before it; `args` or `env` means the flow wrote a different command, usually a different setting.
- A `miss` on one side and a `hit` with the same key on the other means the key is identical and the entry is gone from the cache (evicted, or never uploaded): not a hermeticity problem at all.

## Before committing

The evidence is written to be public: no hostnames, no remote-cache addresses, no home paths. Read it anyway before it leaves the machine; the Confidentiality purge in `CLAUDE.md` still applies.
