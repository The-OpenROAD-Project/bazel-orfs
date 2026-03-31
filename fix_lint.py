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


def find_buildifier():
    """Resolve buildifier from Bazel runfiles."""
    runfiles = find_runfiles()
    if runfiles is None:
        print(
            "error: cannot locate runfiles; " "run via 'bazelisk run //:fix_lint'",
            file=sys.stderr,
        )
        sys.exit(1)
    buildifier = os.path.join(
        runfiles, "buildifier_prebuilt+", "buildifier", "buildifier"
    )
    if not os.access(buildifier, os.X_OK):
        print(
            "error: buildifier not found in runfiles; "
            "run via 'bazelisk run //:fix_lint'",
            file=sys.stderr,
        )
        sys.exit(1)
    return buildifier


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


def run_buildifier(buildifier, files):
    """Format and lint Bazel files with buildifier."""
    if not files:
        return
    print(f"buildifier: {len(files)} file(s)")
    subprocess.check_call([buildifier] + files)
    ret = subprocess.call([buildifier, "-lint", "warn"] + files)
    if ret not in (0, 4):
        raise subprocess.CalledProcessError(ret, "buildifier -lint warn")


def run_mod_tidy(module_files):
    """Regenerate MODULE.bazel.lock for changed MODULE.bazel files."""
    for mf in module_files:
        d = os.path.dirname(mf) or "."
        lockfile = os.path.join(d, "MODULE.bazel.lock")
        if not os.path.isfile(lockfile):
            continue
        if d == ".":
            print("mod tidy: root (with CI config)")
            subprocess.check_call(
                ["bazelisk", "--bazelrc=.github/ci.bazelrc", "mod", "tidy"]
            )
        else:
            print(f"mod tidy: {d}")
            subprocess.check_call(["bazelisk", "mod", "tidy"], cwd=d)


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

    module_files = filter_ignored(
        changed_files(merge_base, "**/MODULE.bazel", "MODULE.bazel"), ignored
    )
    run_mod_tidy(module_files)

    py_files = filter_ignored(changed_files(merge_base, "*.py"), ignored)
    run_black(py_files)

    print("fix_lint: done")


if __name__ == "__main__":
    main()
