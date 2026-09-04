# Idea: a remote cache for ORFS designs, filled after merge

## Context

A fresh clone of bazel-orfs builds OpenROAD, OpenSTA, Yosys, ABC and Qt
from source before the first flow stage runs. The README says 30 to 60
minutes and that is optimistic on a laptop; the reporter of
[#869](https://github.com/The-OpenROAD-Project/bazel-orfs/issues/869) saw
855 seconds for a CTS target *with* a warm disk cache, on a machine that
had already compiled everything once. The first command in the README,
`bazelisk run @orfs//flow/designs/asap7/gcd:gcd_final gui_final`, is a
promise that takes an hour to keep.

None of that work is unique to the user. CI on `main` builds the exact
same tool binaries and, for the designs in `ORFS_TESTS` and `//examples`,
the exact same flow stages, at the exact same pins. Bazel's action cache
keys are content hashes of inputs and command lines, so a user's fresh
clone and a CI runner at the same commit ask for the same keys. Today the
answers stay on the runner, in a GitHub Actions disk cache that only
other runners can read.

OpenROAD has already solved this for itself, and its configuration is
public in its `.bazelrc`:

```
# Anon: HTTPS read-only cache
build --remote_cache=https://bazel.precisioninno.com
build --remote_cache_compression=true
build --remote_upload_local_results=false
# CI: gRPC + Remote Asset API, requires --remote_header
build:ci --remote_cache=grpcs://bazel.precisioninno.com:443
build:ci --experimental_remote_downloader=grpcs://bazel.precisioninno.com:443
```

Everyone reads anonymously over HTTPS. CI jobs that hold the repository
secret add gRPC, the Remote Asset API for archive downloads, uploads, and
an `Authorization: Basic` header derived from the secret. The derived
base64 token is masked in the job log because GitHub masks the raw secret
but not transformations of it. Fork PRs have no secret and get the anon
read path, so nothing untrusted can write. The write happens on push to
`master`, which is the post-merge job this idea is named after.

## Why bazel-orfs cannot simply read OpenROAD's cache

It is tempting to add OpenROAD's anon read line to bazel-orfs's
`.bazelrc` and be done. The keys will not match, for structural reasons
rather than accidental ones:

- **Configuration.** bazel-orfs consumes `@openroad//:openroad` as a
  tool, `cfg = "exec"`, so it is built in the exec configuration
  (`bazel-out/k8-opt-exec-*`). OpenROAD's CI builds it in the target
  configuration with `--config=opt`, which adds `-O3 -flto`, and with
  `--//:platform=gui`. Different configuration, different output paths,
  different flags, different keys.
- **Flags.** bazel-orfs's `.bazelrc` and OpenROAD's set different
  compiler options and features. Every one of them is in the action key.
- **Sources.** These would match. bazel-orfs vendors OpenSTA and ABC into
  the OpenROAD archive at the SHAs `.gitmodules` pins, so file digests
  equal a recursive git checkout's. Source identity is not the problem.

Aligning the first two is possible in principle, but chasing another
project's flag set is a maintenance treadmill and the exec-versus-target
split cannot be aligned at all without changing how bazel-orfs uses the
tool. Better to fill our own keys.

## What bazel-orfs could grow

### 1. A post-merge job that uploads

The CI workflow already runs `bazelisk test ... --build_tests_only` on
every push to `main`. That build produces every artifact worth sharing:
the tool binaries in the exec configuration, and the flow stages of
every design a test depends on, which today means `//examples:mac_final`,
`@orfs//flow/designs/asap7/gcd:gcd_test`,
`@orfs//flow/designs/asap7/uart:uart_test`, the mock-alu build test and
the `//test` flows. Nothing new needs building; the outputs need
somewhere to go.

Copy OpenROAD's job shape rather than inventing one:

```yaml
- name: Run tests
  env:
    BAZEL_CACHE_PASSWORD: ${{ secrets.BAZEL_CACHE_PASSWORD }}
  run: |
    REMOTE_FLAGS=()
    if [ -n "${BAZEL_CACHE_PASSWORD}" ]; then
      TOKEN_B64=$(printf 'ci:%s' "${BAZEL_CACHE_PASSWORD}" | base64 | tr -d '\n')
      echo "::add-mask::${TOKEN_B64}"
      REMOTE_FLAGS=(
        --remote_cache=grpcs://<cache-host>:443
        --experimental_remote_downloader=grpcs://<cache-host>:443
        --remote_upload_local_results=true
        --remote_header="Authorization=Basic ${TOKEN_B64}"
      )
    fi
    bazelisk test ... --build_tests_only "${REMOTE_FLAGS[@]}"
```

The secret is present on `push` to `main` and absent on fork PRs, which
gives the read/write split for free. The existing GitHub Actions disk
cache can stay as a second layer for the runners themselves; OpenROAD
keeps both.

### 2. An anonymous read line in `.bazelrc`

```
common --remote_cache=https://<cache-host>
common --remote_cache_compression=true
common --remote_upload_local_results=false
```

With that in place a fresh clone at a `main` commit finds every tool
binary and every tested flow stage already built. Bazel 9's default
`--remote_download_outputs=toplevel` means only the top-level outputs
are fetched, so the user downloads `openroad-qt`, the ODB and reports of
the stage they asked for, and nothing else. The README's first command
becomes a download, not a compile.

Downstream projects are not covered by our `.bazelrc`, since only the
root module's is read. The line is documented for them to copy, and
`//:bump` could inject it commented out the way it already injects the
OpenROAD from-source boilerplate.

### The trade-off in shipping a cache in `.bazelrc`

OpenROAD's setup works out of the box: clone, build, hit. That is the
whole point for a first-time user, and the reason to copy it. It has a
cost for everyone who is not a first-time user, and the cost needs to be
stated rather than discovered.

`--remote_cache` is single-valued. A user or organisation that already
runs its own remote cache, typically configured in `~/.bazelrc` so it
applies to every project, cannot have both. Bazel reads the workspace
`.bazelrc` first and the home `.bazelrc` after it, and the last value
wins, so the user's cache wins over ours. That is the right precedence,
but it means neither side sees the other:

- With a private cache in `~/.bazelrc`, the project's public cache is
  never consulted. The user pays the first compile of every tool bump
  into their own cache and gets nothing from ours. Hits from the public
  cache and hits from a private one do not add up.
- A `user.bazelrc` pulled in by the workspace `try-import` sits before
  the home rc, so it cannot override a home-rc cache either; only a
  command-line flag or a later rc can.
- `--remote_upload_local_results` and `--remote_header` from a home rc
  also apply to whichever cache ends up selected. Pointing uploads at a
  cache one has no credential for is harmless, the writes are rejected,
  but it is a surprise in the log.

So the project line is a default for people who have nothing, and a
no-op for people who have something better. Both should be true and
documented. The escape hatches are `--remote_cache=` on the command line
or in a later rc to disable, and a home-rc cache to replace. A private
cache that wants the best of both would have to proxy to the public one
as an upstream, which is a server-side feature and out of scope here.

### 3. Conditions for a hit, and how to check them

A user gets a hit only when their action key equals the runner's. The
things that keep that true, and the things that break it:

- `--incompatible_strict_action_env` is already on, so the environment
  is not in the key.
- The C++ toolchain is hermetic, so the host compiler is not in the key.
- `.bazelversion` pins Bazel, and the version is in the key.
- A `user.bazelrc` that changes any build flag misses. So does a
  different `-c` mode or `--config`. So does building at a commit whose
  pins differ from any `main` commit the job has uploaded for, which is
  the normal case on a feature branch until it merges.

Measurement is the `processes:` summary line, which counts remote cache
hits separately, and `--execution_log_compact_file` when a miss needs
attributing to a specific input.

### 4. Which cache server

Two options, in order of preference:

1. **Ask Precision Innovations for a write credential** on the server
   OpenROAD already uses. bazel-orfs is in the same GitHub organisation,
   the server already speaks gRPC and the Remote Asset API, and the
   operational questions (retention, GC, capacity) are already answered
   for OpenROAD's much larger volume. Keys will not collide: they are
   content hashes and the two projects' differ.
2. **Run our own** `bazel-remote` in front of object storage. More
   control, one more thing to operate.

Volume is modest either way. Every OpenROAD bump invalidates every tool
artifact, so the CAS grows by one full toolchain per bump; the design
stage outputs for gcd, uart and the example are small next to a single
`openroad-qt`. Any server with size-based GC copes.

## What this is not

- **Not pinning.** [toolchains.md](toolchains.md) is about deliberate
  non-invalidation: keep using a validated binary although its inputs
  changed. A cache is transparent and invalidates exactly when Bazel
  says so. They compose; neither replaces the other.
- **Not a change to what CI builds.** The job uploads what it already
  builds. Adding designs to the shared cache means adding them to
  `ORFS_TESTS` or `//examples`, with the same "smallest design that
  exercises the feature" discipline `test/BUILD` already states.
- **Not a promise for feature branches.** A branch that bumps OpenROAD
  compiles OpenROAD, once, until it merges and the post-merge job fills
  the keys. That is the right place for the cost.

## Steps

1. Obtain a write credential for `main` CI, or stand up a server.
2. Add the upload flags to the existing test step, gated on the secret.
3. Add the anon read lines to `.bazelrc`.
4. Measure on a fresh clone: the `processes:` line for
   `@orfs//flow/designs/asap7/gcd:gcd_final` should show compiles at
   zero and the flow stages as hits.
5. Update the README's quick start to say what to expect, and give
   downstream projects the line to copy.
