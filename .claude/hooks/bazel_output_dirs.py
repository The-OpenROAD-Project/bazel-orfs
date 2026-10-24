#!/usr/bin/env python3
"""SessionStart hook: this checkout's Bazel output base counts as inside it.

`./bazel-bin`, `./bazel-out` and the other `bazel-*` symlinks point into
the output base under the Bazel output root (`~/.cache/bazel/...` on
Linux), which is outside the project, so Claude Code asks before every
read or copy through them. The output base is a hash of the checkout's
path: every clone and every worktree has its own, on every machine.

At the start of a session this resolves the checkout's own `bazel-*`
symlinks and adds the output bases they point into to
`permissions.additionalDirectories` in `.claude/settings.local.json`, the
checkout's local, never committed settings. Nothing machine-specific is
checked in. The PreToolUse guard (guard_tool.py) still applies its
spelunking rules to those paths: no grep, find or cat in them, only a
small file read by its exact path.

Before the first build there is no `bazel-out` and nothing is added; the
session after the first build picks it up. Entries already in the file
are kept.
"""

import json
import os
import sys

LOCAL_SETTINGS = os.path.join(".claude", "settings.local.json")


def output_bases(project):
    """The output bases the project's `bazel-*` symlinks point into, sorted."""
    bases = set()
    try:
        names = os.listdir(project)
    except OSError:
        return []
    for name in names:
        link = os.path.join(project, name)
        if not name.startswith("bazel-") or not os.path.islink(link):
            continue
        target = os.path.realpath(link)
        # <output base>/execroot/<workspace>/bazel-out/..., or the execroot itself
        marker = os.sep + "execroot" + os.sep
        cut = target.find(marker)
        if cut > 0:
            bases.add(target[:cut])
    return sorted(bases)


def merge(settings, bases):
    """settings with bases in permissions.additionalDirectories, and whether
    anything was added."""
    permissions = settings.setdefault("permissions", {})
    dirs = permissions.setdefault("additionalDirectories", [])
    added = [b for b in bases if b not in dirs]
    dirs.extend(added)
    return settings, bool(added)


def update(project):
    """Add the project's output bases to its local settings; True if written."""
    bases = output_bases(project)
    if not bases:
        return False
    path = os.path.join(project, LOCAL_SETTINGS)
    settings = {}
    if os.path.exists(path):
        with open(path) as f:
            settings = json.load(f)
    settings, changed = merge(settings, bases)
    if not changed:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return True


def main():
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        update(project)
    except (OSError, ValueError) as e:
        # a broken local settings file is the human's to fix; say so, and
        # never stop the session over it
        print("bazel_output_dirs.py: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
