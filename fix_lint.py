#!/usr/bin/env python3
"""Runs all linters/formatters on files changed since origin/main.

Usage: bazelisk run //:fix_lint
"""

import os
import re
import shutil
import subprocess
import sys


def find_runfiles():
    """Locate the runfiles directory."""
    if "RUNFILES_DIR" in os.environ:
        return os.environ["RUNFILES_DIR"]
    # py_binary wrapper: look next to the wrapper script
    candidate = os.path.abspath(sys.argv[0]) + ".runfiles"
    if os.path.isdir(candidate):
        return candidate
    # Inside a .runfiles tree already (e.g. __main__/fix_lint.py)
    for part in __file__.split(os.sep):
        if part.endswith(".runfiles"):
            idx = __file__.index(part) + len(part)
            return __file__[:idx]
    return None


# @buildifier_prebuilt//:buildifier is a plain prebuilt binary up to 6.x and a
# generated bash runner from 8.x on; the repo directory separator is "+" on
# Bazel 7.1+ and "~" before it.  Try every combination rather than pinning one
# layout, so a buildifier_prebuilt bump does not silently break //:fix_lint.
BUILDIFIER_RUNFILES_CANDIDATES = [
    os.path.join("buildifier_prebuilt" + sep, "buildifier", name)
    for sep in ("+", "~")
    for name in ("buildifier", "buildifier.bash")
]


def find_buildifier(runfiles=None):
    """Resolve buildifier from Bazel runfiles."""
    if runfiles is None:
        runfiles = find_runfiles()
    if runfiles is None:
        print(
            "error: cannot locate runfiles; " "run via 'bazelisk run //:fix_lint'",
            file=sys.stderr,
        )
        sys.exit(1)
    for candidate in BUILDIFIER_RUNFILES_CANDIDATES:
        buildifier = os.path.join(runfiles, candidate)
        if os.access(buildifier, os.X_OK):
            return buildifier
    print(
        "error: buildifier not found in runfiles; "
        "run via 'bazelisk run //:fix_lint'",
        file=sys.stderr,
    )
    sys.exit(1)


def get_merge_base():
    """Find the merge base between origin/main and HEAD."""
    try:
        return (
            subprocess.check_output(
                ["git", "merge-base", "origin/main", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        return "HEAD~1"


def load_bazelignore(path=".bazelignore"):
    """Parse .bazelignore, returning a set of ignored directory prefixes."""
    if not os.path.isfile(path):
        return set()
    prefixes = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            prefixes.add(line.rstrip("/"))
    return prefixes


def filter_ignored(paths, ignored_prefixes):
    """Remove paths whose first component matches a .bazelignore entry."""
    result = []
    for p in paths:
        if any(p == d or p.startswith(d + "/") for d in ignored_prefixes):
            continue
        result.append(p)
    return result


def changed_files(merge_base, *pathspecs):
    """Return files changed since merge_base matching pathspecs."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=d", merge_base, "--"]
            + list(pathspecs),
            stderr=subprocess.DEVNULL,
        )
        return [f for f in out.decode().splitlines() if f]
    except subprocess.CalledProcessError:
        return []


BAZEL_PATHSPECS = [
    "*.bzl",
    "*.bazel",
    "BUILD",
    "**/BUILD",
    "MODULE.bazel",
    "**/MODULE.bazel",
    "WORKSPACE",
    "**/WORKSPACE",
]


def buildifier_env():
    """Environment that anchors buildifier's cwd at the workspace root.

    The 8.x bash runner chdirs to $BUILD_WORKING_DIRECTORY -- the directory
    `bazelisk run` was invoked from -- which would break the repo-relative
    paths we hand it whenever that is not the workspace root.  main() has
    already chdir'd to the root, so point the runner at the same place.  The
    6.x binary ignores this.
    """
    env = dict(os.environ)
    env["BUILD_WORKING_DIRECTORY"] = os.getcwd()
    return env


def run_buildifier(buildifier, files):
    """Format and lint Bazel files with buildifier."""
    if not files:
        return
    print(f"buildifier: {len(files)} file(s)")
    env = buildifier_env()
    subprocess.check_call([buildifier] + files, env=env)
    ret = subprocess.call([buildifier, "-lint", "warn"] + files, env=env)
    if ret not in (0, 4):
        raise subprocess.CalledProcessError(ret, "buildifier -lint warn")


def run_black(files):
    """Format Python files with black."""
    if not files or not shutil.which("black"):
        return
    print(f"black: {len(files)} file(s)")
    subprocess.check_call(["black", "--quiet"] + files)


def main():
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    os.chdir(workspace)

    buildifier = find_buildifier()
    merge_base = get_merge_base()
    ignored = load_bazelignore()

    bazel_files = filter_ignored(changed_files(merge_base, *BAZEL_PATHSPECS), ignored)
    run_buildifier(buildifier, bazel_files)

    py_files = filter_ignored(changed_files(merge_base, "*.py"), ignored)
    run_black(py_files)

    print("fix_lint: done")


if __name__ == "__main__":
    main()
