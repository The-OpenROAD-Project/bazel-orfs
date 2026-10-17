# Solved problems: hermetic

What the clean build gives you, and how `bazelisk run //:host_tools`
keeps it that way. The [README](../README.md) says where this fits: the
place an answer ends up once the [dirty lane](dirty-lane.md) has found
it.

**Nothing to install.** Bazel downloads, builds and caches every
dependency: OpenROAD, OpenSTA, Yosys, ABC, GNU Make, Qt, Python, the C++
toolchain and the PDKs. A developer machine or a CI runner needs Bazelisk
and a standard Linux install, and gets a bit-for-bit reproducible flow. No
Docker, no `apt install`, no "works on my machine". The RHEL 8 story in
[bazel-orfs #869](https://github.com/The-OpenROAD-Project/bazel-orfs/issues/869)
is what this buys you: the two things that broke were a host `curl` and a
host Python that had leaked into the build, and both were fixed by making
them hermetic.

"A standard Linux install" is meant literally, and `bazelisk run
//:host_tools` holds the line. What is used from the host, and nowhere
else, is:

- **Base tools** — `curl`, `sha256sum`, `tar`, `sed`, `find`, `nproc` and
  the rest of coreutils/findutils/gawk. OpenROAD's `archive_override`
  vendors three git submodules through `curl` + `sha256sum -c`, because a
  GitHub `/archive/<sha>.tar.gz` does not carry submodules and
  `archive_override`'s `integrity` does not cover bytes fetched by
  `patch_cmds`. The curl flags stay within reach of curl 7.52 (2016) on
  purpose; RHEL 8 ships 7.61.
- **`python3`** — for a fetch-phase repository rule
  (`private/designs.bzl` parses every ORFS `config.mk`), the mock tools,
  and `//tools/pin`. Every such file stays parseable by Python 3.6, the
  oldest `python3` on a distro still receiving updates.

Not needed, and checked: `jq`, `yq`, `perl`, `bc`, `docker`, `cmake`,
`wget`, `rsync`, `unzip`, `xz`. `yq` is fetched by Bazel with a pinned
SHA256 rather than expected on the host; GNU Make is built from source.
`klayout` is the one opt-in exception — the default is a mock, see
[klayout.md](klayout.md).

**Plumbing an AI understands.** bazel-orfs has turned out to be the
right shape for AI-assisted work. Every input is a label, every stage is a
target, every variable is checked against ORFS's own `variables.yaml`, and
a stage that fails can be re-run outside the sandbox with one command. An
AI assistant wires up a new design, a new PDK or a patched tool without
being told how, because there is exactly one way to do each of those
things and the build tells you when you got it wrong.

**All of Bazel, all of ORFS.** Artifacts, parallel builds, remote caching,
remote execution, and a flow that only rebuilds the stages a change
touches. ORFS is used unmodified, so you get the latest OpenROAD and ORFS
features, the ORFS debugging tools such as `make issue` and
`deltaDebug.py`, and GitHub issues you file are immediately actionable for
the OpenROAD and ORFS maintainers.
