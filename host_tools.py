#!/usr/bin/env python3
"""The host tools bazel-orfs is allowed to rely on.

README.md promises that a developer machine or a CI runner needs nothing
but Bazelisk and a standard Linux install.  Two things quietly break that
promise if nobody is watching:

1. A shipped script, or a patch_cmds entry, reaching for a tool a stock
   install does not have -- `jq`, `yq`, `perl`, `bc`, `docker`, `cmake`.

2. A Python file that the *host* interpreter runs -- not the hermetic
   toolchain -- using syntax newer than the oldest supported distro's
   `python3`.  RHEL 8 and SLES 15 ship 3.6, Ubuntu 20.04 ships 3.8, and a
   fetch-phase repository rule or a `bazel run` wrapper gets whatever is
   on PATH.  That is not a warning: it is a SyntaxError before the first
   line runs, and it had already happened -- tools/pin/pin.py carried a
   match statement, so `//tools/pin` was dead on every distro older than
   Python 3.10.

Rule 1 is a denylist on purpose.  Recognising every command in a shell
script needs a shell parser; a regex that guesses produces false positives
until someone deletes the test.  Naming what we have decided not to depend
on is precise, and a genuinely new dependency is usually one of these.

Run it: `bazelisk run //:host_tools`.  CI runs it after the public surface
check.  Reads the tree through git, so it is a run, not a hermetic test;
//test:host_tools_test covers the rules.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

# Oldest `python3` on a distro still receiving updates: RHEL 8 / SLES 15.
HOST_PYTHON_FLOOR = (3, 6)

# Python files the host interpreter runs, each with the caller that does
# it.  Everything else runs under the hermetic toolchain (py_binary,
# py_test) and may use whatever that toolchain supports.
HOST_PYTHON = {
    "config_mk_parser.py": 'private/designs.bzl: repository_ctx.which("python3")',
    "tools/pin/pin.py": "tools/pin/pin.sh.tpl: python3 ${PINNER}",
    "mock/klayout/src/bin/klayout.py": "mock/klayout/src/bin/klayout.sh: exec python3",
    "mock/openroad/src/bin/openroad.py": "mock/openroad/src/bin/openroad.sh: exec python3",
    "mock/yosys/src/bin/yosys.py": "mock/yosys/src/bin/yosys.sh: exec python3",
    "bump.py": "runs standalone, before any toolchain exists",
    "bump_impl.py": "bump.py: subprocess.run([sys.executable, local_impl])",
}

# Files that invoke the host python3.  Kept equal to what a scan of the
# shipped surface finds, so a new call site has to be declared -- and with
# it, the version floor the file it runs now has to respect.
HOST_PYTHON_CALLERS = frozenset(
    [
        "mock/klayout/src/bin/klayout.sh",
        "mock/openroad/src/bin/openroad.sh",
        "mock/yosys/src/bin/yosys.sh",
        "mock_klayout.bzl",
        "private/designs.bzl",
        "tools/pin/pin.sh.tpl",
    ],
)

# Tools we have decided not to depend on: absent from a minimal install of
# at least one still-supported distro, or hermetic here by design -- yq is
# downloaded with a pinned SHA256 by load_json_file.bzl, and cmake is
# banned outright because bazel is the only build path.
#
# Removing an entry is a decision about what a consumer must install.
DENIED_TOOLS = frozenset(
    """
    jq yq perl bc column shuf getopt flock docker podman cmake ccmake ninja meson
    wget rsync scp unzip zip xz zstd bzip2 numfmt pip pip3 conda brew apt apt-get
    yum dnf pacman zypper snap gh xdg-open klayout
    """.split(),
)

# Where a denied tool is nevertheless tolerated, and why.
TOLERATED = {
    # Dev convenience: opens a report in a browser. Fails loudly, and no
    # build depends on it.
    "open_html.sh": {"xdg-open"},
    # Opt-in escape hatch. The default klayout is @mock_klayout, so a stock
    # consumer never runs this. See docs/klayout.md.
    "klayout.sh": {"klayout"},
}

# Not shipped: tests, captured reproducers, scratch, agent tooling, docs
# and CI.  mock/ *is* shipped -- @mock_klayout is the default klayout.
EXCLUDED = (
    ".agents/",
    ".claude/",
    ".github/",
    "docs/",
    "gallery/",
    "test/",
    "tmp/",
)

SCANNED_SUFFIXES = (".sh", ".tpl", ".bzl", ".bazel")

HOST_PYTHON_CALL = re.compile(r'(?:exec\s+)?python3?\s+["$]|which\("python3"\)')

# `#` starting a word through end of line.  Crude, but a denied tool named
# in a comment is not a dependency and should not fail the check.
COMMENT = re.compile(r"(?:^|\s)#.*$", re.MULTILINE)

# One patch_cmds entry: a string at archive_override's list indentation.
PATCH_CMD = re.compile(r'^\s{8}"(.*)",$', re.MULTILINE)


def python_floor(source):
    """Lowest 3.x that parses this source, as a (3, minor) tuple."""
    for minor in range(4, 20):
        try:
            ast.parse(source, feature_version=(3, minor))
        except SyntaxError:
            continue
        return (3, minor)
    return None


def denied_tools_in(text, tolerated=frozenset()):
    """Denied tools appearing where a command goes.

    Matching the bare name anywhere hits prose -- an `echo` explaining a
    table column is not a dependency on column(1) -- so the name has to sit
    at the start of a line or after a `;`, `|`, `&&`, `$(` or `exec`.
    """
    text = COMMENT.sub("", text)
    return sorted(
        tool
        for tool in DENIED_TOOLS - frozenset(tolerated)
        if re.search(
            r"(?:^|[;&|(]|&&|\|\||\bexec\b|\$\()\s*%s(?![-\w])" % re.escape(tool),
            text,
            re.MULTILINE,
        )
    )


def shipped(files):
    return [f for f in files if not str(f).startswith(EXCLUDED)]


def _read(root, path):
    return (root / path).read_text(encoding="utf-8", errors="replace")


def check(root, files):
    """Every host-tool violation in `files`, as a list of messages."""
    problems = []
    paths = shipped(files)

    for path, caller in sorted(HOST_PYTHON.items()):
        if not (root / path).exists():
            problems.append(
                "%s is declared as host-run python but does not exist; "
                "update HOST_PYTHON in host_tools.py" % path,
            )
            continue
        floor = python_floor(_read(root, path))
        if floor is None:
            problems.append("%s does not parse as python at all" % path)
        elif floor > HOST_PYTHON_FLOOR:
            problems.append(
                "%s needs python %d.%d, but the host interpreter runs it "
                "(%s) and that is %d.%d on the oldest supported distro"
                % (path, floor[0], floor[1], caller, *HOST_PYTHON_FLOOR),
            )

    found = {
        str(f)
        for f in paths
        if str(f).endswith(SCANNED_SUFFIXES) and HOST_PYTHON_CALL.search(_read(root, f))
    }
    for path in sorted(found - HOST_PYTHON_CALLERS):
        problems.append(
            "%s runs the host python3 without being declared; add it to "
            "HOST_PYTHON_CALLERS and the file it runs to HOST_PYTHON, so "
            "that file's version floor is checked -- or use a py_binary "
            "and the hermetic interpreter instead" % path,
        )
    for path in sorted(HOST_PYTHON_CALLERS - found):
        problems.append(
            "%s no longer runs the host python3; drop it from "
            "HOST_PYTHON_CALLERS" % path,
        )

    for f in paths:
        if not str(f).endswith((".sh", ".tpl")):
            continue
        for tool in denied_tools_in(
            _read(root, f),
            TOLERATED.get(os.path.basename(str(f)), frozenset()),
        ):
            problems.append(
                "%s runs %s, which a stock Linux install may not have" % (f, tool),
            )

    module = root / "MODULE.bazel"
    if module.exists():
        for cmd in PATCH_CMD.findall(module.read_text(encoding="utf-8")):
            for tool in denied_tools_in(cmd):
                problems.append(
                    "a patch_cmds entry runs %s, which a stock Linux install "
                    "may not have -- and patch_cmds run before any toolchain "
                    "exists" % tool,
                )

    return problems


def tracked_files(root):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [Path(p.decode()) for p in out.split(b"\0") if p]


def main(argv):
    root = Path(
        argv[1] if len(argv) > 1 else os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."),
    ).resolve()
    problems = check(root, tracked_files(root))
    for p in problems:
        print(p)
    if problems:
        print("\n%d host-tool violation(s); see host_tools.py" % len(problems))
        return 1
    print("host tools: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
