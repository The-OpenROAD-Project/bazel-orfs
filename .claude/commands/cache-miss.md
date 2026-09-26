> **Repo**: Run from the bazel-orfs root. Applies to any target, and was written for `//test/coremark_joule/designs/asap7/xiangshan:XSTile_grt`, whose cold build is six hours.

Two questions, one tool. *Is this target a remote cache hit here?* is a capture that never executes an action, minutes on any machine, a laptop included. *Why is it not, when another machine built it?* is a diff of two captures, which names the first action whose key differs, the part of the key that moved, and the source file behind it. Never commit an execution log; the evidence is a few kilobytes and is committed next to the design.

ARGUMENTS: $ARGUMENTS

## Check the cheap explanation first

**Is the other machine on the same tree?** Every ORFS stage action, synthesis included, takes the whole patched ORFS `flow/scripts` tree as input: the synthesis canonicalize action's inputs include `global_place.tcl`, `global_route.tcl`, `detail_place.tcl` and `variables.yaml`. So one carried patch in `patches/` for global placement changes the key of every stage from synthesis on, and a patch to OpenROAD itself changes the `openroad` binary, which every stage also takes as input. A day with a batch of carried patches is a day nothing built before it is reusable. The `tree` line of two evidence files settles most cases; `git log -1` does not, because a commit hash dies in a rebase and the tree hash does not.

## Two roles

**A builder** has the memory and the hours: it builds the target with uploading on, then captures and commits the evidence in the same pull request as the design change that moved the keys. The evidence then witnesses what the cache was given.

**A consumer** (a laptop) never builds a flow stage. It asks whether the target is cached, and if not, diffs its capture against the committed one to learn which. A capture on a consumer downloads the inputs of each miss (the placed database a CTS miss needs is 1.6 GB on XiangShan's MemBlock) and computes nothing; the build of the target itself belongs on the builder.

## What is already known to be hermetic

Measured, so you do not measure it again unless something changed:

- **The Chisel to FIRRTL chain.** `//test/coremark_joule/xiangshan:xiangshan_fir` from a brand-new output base, reading the remote cache only: all 951 spawns (Scalac, Javac, espresso's C, protobuf, the fir genrule) were remote hits, so the fetched Maven jars, XiangShan archives, Scala toolchain and firtool are byte-identical from one fetch to the next. The generator runs on `remotejdk11`, not the host JDK.
- **C++ tools.** yosys, abc, make and OpenROAD build with the hermetic `@llvm` toolchain, so the host gcc does not matter.
- **Action environments.** `--incompatible_strict_action_env`: `PATH=/bin:/usr/bin:/usr/local/bin`, `PWD=/proc/self/cwd`, no home paths in any command line.
- **One host input, harmless today.** `@ncurses//:local_terminfo` is a symlink to the host's `/usr/share/terminfo`, an input of `@ncurses//:fallback_c`. That genrule's key differs between distros, but ncurses is built with no fallback terminals, so `fallback.c` is the same stub everywhere and nothing downstream moves. The evidence witnesses it anyway (the `terminfo` line), and on a distro nobody built on before, that genrule is the one `ran` a capture reports: it finishes before it can be killed and its output is the same stub.

## Is it cached?

```sh
bazelisk run //tools/cache_evidence -- capture \
  //test/coremark_joule/designs/asap7/xiangshan:XSTile_cts --out -
```

Prints the evidence and ends with a summary: the counts, every miss, every action left unreached behind one, or `every action is a remote cache hit`. Exit status 0 means exactly that; 1 means something is missing. Minutes: a repository fetch, an analysis, one cache lookup per action.

`capture` never executes an action, and three choices make that true; each exists because the obvious alternative was tried and failed:

- **A fresh output base** (under `./tmp/cache_evidence/`, deleted afterwards). Bazel logs no spawn that was a local action-cache hit, so on the machine that built the target an ordinary run logs nothing at all.
- **A miss is killed the moment it appears.** Every action is spawned sandboxed, and a thread kills whatever process appears under the output base's sandbox directory, so a miss fails in a blink, logged with its inputs, and `--keep_going` carries the build to every other action whose inputs exist. Remote hits never spawn a process; the strategy is not part of any key. This replaced blocking `/usr` and `/bin` in linux-sandbox, which Ubuntu's AppArmor denies unprivileged users, and interrupting the client, which left the server computing the miss for as long as the stage takes. `--experimental_remote_require_cached` fails an action only after it has run, and `--spawn_strategy=remote` with no executor fails every action before the cache is asked, so neither helps. An action so short it finished before it could be killed is logged as `ran`: not a hit, and not uploaded.
- **Actions behind a miss are listed, not omitted.** Their inputs were never produced, so Bazel cannot key them. `capture` asks `aquery` for the in-scope actions and lists every one the log lacks as `not_reached`. Without this an XSTile stage that was never keyed looked no different from one that was never in the graph.

## Collecting the evidence to commit

On the builder, from the tree the target was built from:

```sh
bazelisk run //tools/cache_evidence -- capture \
  //test/coremark_joule/designs/asap7/xiangshan:XSTile_grt \
  --out test/coremark_joule/designs/asap7/xiangshan/cache_evidence/builder.txt
```

Name the file for the role, not the host (`builder`, `consumer`, `machine_a`): a hostname does not belong in a public repository. On a consumer, the same command with `consumer.txt`. Then diff:

```sh
bazelisk run //tools/cache_evidence -- diff \
  $PWD/test/coremark_joule/designs/asap7/xiangshan/cache_evidence/builder.txt \
  $PWD/test/coremark_joule/designs/asap7/xiangshan/cache_evidence/consumer.txt
```

Only key evidence is kept: the compact execution log of the XSCore_grt graph is 5 MB compressed and 90 MB raw; the evidence is tens of kilobytes.

## Reading the evidence and the diff

An evidence file has, in order:

- `target`, `bazel`, `commit ... dirty`, `tree` (the whole source tree), `design_tree` (the target's package), `host` (distro, libc, architecture), `terminfo`;
- `option` lines: what `--announce_rc` reports. Values of options that name private infrastructure (remote cache, headers, credentials) and home paths are written as `<redacted>`, not hashed, since a short hash of a guessable hostname confirms the guess. `--remote_upload_local_results` and `--remote_cache_compression` keep their value when it is a switch: whether a machine uploads is what a later miss needs to know. `capture` refuses to write a line that still looks like an address, a home path or an email;
- `spawns N hit H ran R miss M not_reached K` for the whole graph;
- `tool <digest> <files> <group>`: each tool the in-scope actions run (the openroad and yosys binaries, yosys's share directory, the python wrapper's runfiles tree, make, klayout's mock);
- `input <digest> <path>`: every source file of this workspace an in-scope action reads (the design's config, constraints, pin plans), so a moved design digest is traced to a file;
- `spawn <key> <hit|ran|miss> <mnemonic> <first output> args= env= tools= sources= design=`: every action under `--scope` (default `//test/`), with its remote cache key and separate digests of its arguments, environment, tools, external sources and design inputs;
- `not_reached <mnemonic> <first output>`: every in-scope action the build never keyed because an action before it missed.

`diff` prints what differs, most fundamental first, and ends with the first differing action:

- `bazel:`, `commit:`, `tree:`, or `option only in ...`: a different Bazel, tree or flag set. Every key can move; fix that before reading further. A commit `not in this history` was captured on a branch that was rebased; the `tree` line says whether its sources were nevertheless the same. `same tree:` means they were, so look at tools and options.
- `tool <group>`: a tool binary differs. If the trees match, that tool's build is not reproducible across the machines; rerun `capture` with `--scope` set to the tool's repository (`@@openroad+//`, for instance) to itemise its build.
- `input <path>`: a source file of the design differs between the trees.
- The first differing `spawn`, and the part that moved: `sources` means the patched ORFS tree or a PDK file differs (a carried patch, a bump); `design` means a source file (named on the same line as `source files moved`) or an upstream action's output differs, so look at the spawn before it; `args` or `env` means the flow wrote a different command, usually a different setting.
- A `miss` on one side and a `hit` with the same key on the other means the key is identical and the entry is gone from the cache (evicted, or never uploaded): not a hermeticity problem at all.

## What committed evidence promises

A committed evidence file witnesses one thing: at tree T, machine M saw these hits, with uploading on or off as its option line says. It is not a promise that the cache still holds them. A miss found later has one of three causes, and the diff separates them:

1. **The inputs moved.** The keys differ; the diff names the tree, the tool or the source file. The committed evidence is stale by exactly that change, and the builder that made the change recaptures.
2. **Never uploaded.** The keys are equal, the committed side says `hit`, and its `--remote_upload_local_results` line says `false`, or the machine that built on the new inputs never captured at all. Nothing was ever given to the cache under this key.
3. **Evicted.** The keys are equal, the committed side says `hit` with uploading on, this side says `miss`. The cache dropped it; the builder rebuilds and uploads.

So: **a pull request that changes a design's inputs recaptures that design's evidence**, on the builder, after the build, in the same pull request, so main always carries evidence for the tree it is at. The design's README carries one line naming the target last seen fully cached, its tree hash, the date and the evidence file, under the dogfooding rule that a README says what is.

## Before committing

The evidence is written to be public: no hostnames, no remote-cache addresses, no home paths. Read it anyway before it leaves the machine; the Confidentiality purge in `CLAUDE.md` still applies.
