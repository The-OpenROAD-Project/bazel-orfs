#!/usr/bin/env python3
"""Give a workspace that depends on bazel-orfs the skills, the rules and
the odb-debug MCP server bazel-orfs's own agents work with, at the version
its MODULE.bazel pins.

    bazelisk run @bazel-orfs//:agent -- setup    # once; commit what it lists
    bazelisk run @bazel-orfs//:agent -- sync     # every session, from the hook

Nothing is copied. `sync` links the workspace to the bazel-orfs source
Bazel fetched for the pin:

    .claude/bazel-orfs           -> <output_base>/external/bazel-orfs+
    .claude/skills/<name>        -> ../bazel-orfs/.claude/skills/<name>

and keeps those links out of git through the clone's info/exclude, so a
bump changes what the links show and no committed file. `setup` runs
`sync` and adds the three committed entries that use the links: the
odb-debug server in .mcp.json, a SessionStart hook in
.claude/settings.json that runs `sync`, and an import of
docs/agent-rules.md in CLAUDE.md.

A path that is in the way and is not one of these links is refused, never
overwritten: a skill of the workspace's own with an exported name, an
.mcp.json odb-debug entry that says something else.
"""

import json
import os
import subprocess
import sys

# The skills a workspace that depends on bazel-orfs gets. Every skill in
# .claude/skills is either here or in INTERNAL_SKILLS, which agent_test
# asserts, so a new skill is a decision, not a default.
EXPORTED_SKILLS = (
    "analyze-before-push",
    "byo-openroad",
    "cache-miss",
    "check-setup",
    "debug-rtl-sim",
    "dirty-lane",
    "dogfooding",
    "macro-constraints",
    "macro-selection",
    "new-project",
    "no-paint-drying",
    "odb-debug",
    "openroad-debug",
    "orfs-deps-preflight",
    "prefer-slang",
    "repair-headroom",
    "repair-timing-grt",
    "scale-to-memory",
    "surgery",
    "warm-gui",
)

# bazel-orfs's own: its pull requests and studies, GitHub housekeeping,
# its ideas/ directory, and reporting OpenROAD bugs upstream.
INTERNAL_SKILLS = (
    "github-deprecations",
    "idea",
    "odb-to-cpp",
    "openroad-issue",
    "study-pr",
    "untar-and-run-report",
)

LINK = os.path.join(".claude", "bazel-orfs")
SKILLS = os.path.join(".claude", "skills")
# A skill link points through LINK, so a moved output base is one link.
LINKED_SKILLS = os.path.join(LINK, ".claude", "skills")

MCP_SERVER = "odb-debug"
MCP_ENTRY = {
    "command": "python3",
    "args": [".claude/bazel-orfs/tools/odb_debug/mcp_server.py"],
    "env": {"ODB_DEBUG_DIR": "tmp/odb-debug"},
}

# A build holding the Bazel lock makes the hook wait; past this the hook
# is dropped and the session starts on the links the last sync left.
HOOK_COMMAND = "bazelisk run --noshow_progress @bazel-orfs//:agent -- sync --hook"
HOOK = {
    "matcher": "startup",
    "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 60}],
}

RULES_IMPORT = "@.claude/bazel-orfs/docs/agent-rules.md"

EXCLUDE_BEGIN = (
    "# >>> bazel-orfs agent links (bazelisk run @bazel-orfs//:agent -- sync)"
)
EXCLUDE_END = "# <<< bazel-orfs agent links"


class Refused(Exception):
    pass


def repo_root():
    """The bazel-orfs source tree this binary was built from."""
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _replace_link(path, target):
    """Point the symlink at path to target; True if it changed."""
    if os.path.islink(path):
        if os.readlink(path) == target:
            return False
        os.remove(path)
    elif os.path.lexists(path):
        raise Refused("%s is in the way and is not a link; move it" % path)
    os.symlink(target, path)
    return True


def _ours(path, target):
    return os.path.islink(path) and os.readlink(path).startswith(target + os.sep)


def _skills_dir(workspace):
    """Where the skill links go, relative to the workspace: .claude/skills,
    or the directory it links to when the workspace shares one skills
    directory between agents. The links are made there, relative to it,
    and git sees them there."""
    skills = os.path.realpath(os.path.join(workspace, SKILLS))
    rel = os.path.relpath(skills, os.path.realpath(workspace))
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise Refused("%s points outside the workspace, to %s" % (SKILLS, skills))
    return rel


def sync(workspace, root, run=subprocess.run):
    """Make the links; the list of workspace-relative paths they occupy and
    whether anything changed."""
    if os.path.realpath(workspace) == os.path.realpath(root):
        raise Refused(
            "this is bazel-orfs itself; its skills are already in .claude/skills"
        )
    missing = [
        s
        for s in EXPORTED_SKILLS
        if not os.path.isfile(os.path.join(root, ".claude", "skills", s, "SKILL.md"))
    ]
    if missing:
        raise Refused("%s has no skill(s) %s" % (root, ", ".join(missing)))
    skills_rel = _skills_dir(workspace)
    skills = os.path.join(workspace, skills_rel)
    target = os.path.relpath(LINKED_SKILLS, skills_rel)
    in_the_way = [
        os.path.join(skills_rel, s)
        for s in EXPORTED_SKILLS
        if os.path.lexists(os.path.join(skills, s))
        and not _ours(os.path.join(skills, s), target)
    ]
    if in_the_way:
        raise Refused(
            "the workspace has its own %s; bazel-orfs exports skills by those"
            " names" % ", ".join(in_the_way)
        )

    os.makedirs(skills, exist_ok=True)
    changed = _replace_link(os.path.join(workspace, LINK), root)
    for s in EXPORTED_SKILLS:
        changed |= _replace_link(os.path.join(skills, s), os.path.join(target, s))
    for name in sorted(os.listdir(skills)):
        path = os.path.join(skills, name)
        if name not in EXPORTED_SKILLS and _ours(path, target):
            os.remove(path)
            changed = True

    paths = [LINK] + [os.path.join(skills_rel, s) for s in EXPORTED_SKILLS]
    exclude_from_git(workspace, paths, run)
    return paths, changed


def exclude_from_git(workspace, paths, run=subprocess.run):
    """Keep the links out of git in this clone (they point into this
    machine's output base), in a block of info/exclude this tool owns."""
    try:
        out = run(
            ["git", "rev-parse", "--git-path", "info/exclude"],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        )
    except OSError:
        return
    if out.returncode != 0:
        return
    exclude = os.path.join(workspace, out.stdout.strip())
    try:
        with open(exclude) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    block = "\n".join(
        [EXCLUDE_BEGIN] + ["/" + p.replace(os.sep, "/") for p in paths] + [EXCLUDE_END]
    )
    if EXCLUDE_BEGIN in text:
        head, _, rest = text.partition(EXCLUDE_BEGIN)
        _, _, tail = rest.partition(EXCLUDE_END)
        new = head + block + tail
    else:
        new = text + ("" if text.endswith("\n") or not text else "\n") + block + "\n"
    if new != text:
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "w") as f:
            f.write(new)


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def setup_mcp(workspace):
    """Add the odb-debug server to .mcp.json; True if it changed."""
    path = os.path.join(workspace, ".mcp.json")
    data = _load_json(path)
    servers = data.setdefault("mcpServers", {})
    if servers.get(MCP_SERVER) == MCP_ENTRY:
        return False
    if MCP_SERVER in servers:
        raise Refused(
            ".mcp.json already has an %r server that is not bazel-orfs's: %s"
            % (MCP_SERVER, json.dumps(servers[MCP_SERVER]))
        )
    servers[MCP_SERVER] = MCP_ENTRY
    _write_json(path, data)
    return True


def setup_hook(workspace):
    """Add the SessionStart sync hook to .claude/settings.json; True if it
    changed."""
    path = os.path.join(workspace, ".claude", "settings.json")
    data = _load_json(path)
    entries = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    for entry in entries:
        for hook in entry.get("hooks", []):
            if hook.get("command") == HOOK_COMMAND:
                return False
    entries.append(HOOK)
    _write_json(path, data)
    return True


def setup_rules(workspace):
    """Import the shared rules into CLAUDE.md; True if it changed."""
    path = os.path.join(workspace, "CLAUDE.md")
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    if RULES_IMPORT in text.split("\n"):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    if text:
        text += "\n"
    text += (
        "The rules and skills for working on ORFS flows come from bazel-orfs, at\n"
        "the version MODULE.bazel pins (`bazelisk run @bazel-orfs//:agent -- setup`):\n"
        "\n" + RULES_IMPORT + "\n"
    )
    with open(path, "w") as f:
        f.write(text)
    return True


def main(argv):
    args = argv[1:]
    if not args or args[0] not in ("setup", "sync"):
        sys.stderr.write(__doc__)
        return 2
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        sys.stderr.write("run it with `bazelisk run @bazel-orfs//:agent -- ...`\n")
        return 2
    try:
        _, changed = sync(workspace, repo_root())
        if args[0] == "sync":
            if "--hook" in args:
                # Claude Code lists skills before SessionStart hooks finish;
                # a link made now is seen this session only after a reload.
                if changed:
                    print(
                        json.dumps(
                            {
                                "hookSpecificOutput": {
                                    "hookEventName": "SessionStart",
                                    "reloadSkills": True,
                                }
                            }
                        )
                    )
            else:
                print("linked %s and %d skills" % (LINK, len(EXPORTED_SKILLS)))
            return 0
        wrote = [
            name
            for name, did in (
                (".mcp.json", setup_mcp(workspace)),
                (".claude/settings.json", setup_hook(workspace)),
                ("CLAUDE.md", setup_rules(workspace)),
            )
            if did
        ]
    except Refused as e:
        # Exit 2: a SessionStart hook shows the user stderr only for 2.
        sys.stderr.write("@bazel-orfs//:agent: %s\n" % e)
        return 2
    print("linked %s and %d skills (kept out of git)" % (LINK, len(EXPORTED_SKILLS)))
    if wrote:
        print("updated, commit these: %s" % ", ".join(wrote))
    else:
        print("already set up")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
