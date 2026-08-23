#!/usr/bin/env python3
"""PreToolUse guard shared by Claude Code and antigravity.

This file is the single source of truth for the repository's hard stops.
Antigravity reaches the very same file through the
``.agents/scripts/guard_tool.py`` symlink, so a rule can never be live for one
agent and missing for the other.

The two agents speak different hook dialects, which this script normalizes:

===============  ==============================  ============================
                 Claude Code                     antigravity
===============  ==============================  ============================
request          ``{"tool_name", "tool_input"}``  ``{"toolCall": {...}}``
shell tool       ``Bash`` / ``command``           ``run_command`` / ``CommandLine``
deny response    ``{"hookSpecificOutput": ...}``  ``{"decision": "deny"}``
allow response   *no output at all*               ``{"decision": "allow"}``
===============  ==============================  ============================

Claude Code reads ``permissionDecision: "allow"`` as *skip the permission
prompt entirely*, so answering "allow" would silently auto-approve every tool
call in the session. We therefore emit nothing unless we are denying, which
leaves the normal permission flow untouched.

Rather than enumerating tool names, the normalizer picks up whichever
command/path keys are present in the payload. New tools are covered
automatically as long as they use the conventional argument names.

``--explain`` prints the policy as markdown. ``guard_tool_test.py`` asserts
that the "AI Guardrails" section of CLAUDE.md is exactly that output, so the
prose can never drift from what is actually enforced.
"""

import json
import re
import sys

# Keys the two dialects use for the shell command, the working directory, and
# file/directory paths. Collected by name so we do not have to track tool names.
COMMAND_KEYS = ("command", "CommandLine")
CWD_KEYS = ("cwd", "Cwd")
PATH_KEYS = (
    "file_path",
    "notebook_path",
    "path",
    "AbsolutePath",
    "TargetFile",
    "SearchPath",
    "DirectoryPath",
)

# Shell separators. Command rules are evaluated per segment so that an
# innocent segment cannot be flagged by a neighbour's arguments.
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")

# `bazel`, `bazelisk`, `bazel-7.4.0`, `/usr/bin/bazel` — but not `bazel-orfs`.
BAZEL = r"(?<![\w.-])(?:bazelisk|bazel-[0-9][\w.]*|bazel)(?![\w-])"
BAZEL_CLEAN = re.compile(BAZEL + r"(?:\s+--?\S+)*\s+clean(?![\w-])")

BAZEL_OUTPUT_DIR = re.compile(r"(^|/)bazel-(out|bin|testlogs)(/|$)")
CACHE_DIR = re.compile(r"(^|/)\.cache(/|$)")
# Matches /tmp and /tmp/..., but not ./tmp or /somewhere/tmp.
TMP_DIR = re.compile(r"^/tmp(/|$)")
TMP_IN_COMMAND = re.compile(r"(?<![\w./])/tmp(?:/|(?![\w/]))")

READ_TOOLS = r"find|grep|tree|ls|fd|rg|cat|head|tail|less|sed|awk|wc|diff"
SPELUNK_IN_COMMAND = re.compile(
    r"\b(?:" + READ_TOOLS + r")\b[^;&|]*"
    r"(?:\bbazel-(?:out|bin|testlogs)\b|(?<![\w-])\.cache\b)"
)

GIT_LOCAL_MUTATE = re.compile(
    r"\bgit\s+(?:-c\s+\S+\s+)*"
    r"(?:checkout|switch|rebase|cherry-pick|merge|reset|pull)\b"
)
# `origin/main`, `upstream/master`, ... — a remote-tracking ref is always fine.
REMOTE_REF = re.compile(r"\b[\w.-]+/(?:master|main)\b")
PROTECTED_REF = re.compile(r"(?<![\w\-/])(?:master|main)(?![\w\-])")

TMP_MESSAGE = "Using /tmp is forbidden (it is small and shared). Always use ./tmp."


def segments(command):
    """Split a shell command line into independently-evaluated segments."""
    return [part.strip() for part in SEGMENT_SPLIT.split(command) if part.strip()]


def touches_protected_branch(segment):
    """True if the segment names a local `main`/`master`, ignoring remote refs."""
    return PROTECTED_REF.search(REMOTE_REF.sub("", segment)) is not None


def spelunk_message(text):
    """Explain the least-bad alternative for this particular spelunk."""
    lowered = text.lower()
    if "bazel-testlogs" in lowered:
        return (
            "Do not read raw bazel-testlogs directly to avoid context explosion. "
            "Extract failures using a targeted script."
        )
    if "netlist" in lowered or "bazel-bin" in lowered:
        return (
            "Do not grep raw generated files in bazel-bin or netlists to avoid "
            "context explosion."
        )
    if "cache" in lowered or "external" in lowered:
        return (
            "Do not spelunk in bazel cache. Clone dependencies into ./tmp if you "
            "need to inspect or patch them."
        )
    return (
        "Spelunking in bazel-* or .cache output directories is forbidden as it "
        "causes context explosion and wastes time."
    )


def check_bazel_clean(request):
    for segment in segments(request.command):
        if BAZEL_CLEAN.search(segment):
            return "bazelisk clean and bazel clean => verboten, protects bazel cache."
    return None


def check_git_local_branch(request):
    for segment in segments(request.command):
        if GIT_LOCAL_MUTATE.search(segment) and touches_protected_branch(segment):
            return (
                "git checkout/switch/rebase/cherry-pick/merge/reset/pull "
                "master => verboten. Always use origin/master directly "
                "(detached HEAD) or use git worktree."
            )
    return None


def check_spelunking(request):
    for segment in segments(request.command):
        if SPELUNK_IN_COMMAND.search(segment):
            return spelunk_message(segment)
    for path in request.paths:
        if BAZEL_OUTPUT_DIR.search(path) or CACHE_DIR.search(path):
            return spelunk_message(path)
    return None


def check_tmp(request):
    if request.command and TMP_IN_COMMAND.search(request.command):
        return TMP_MESSAGE
    for path in request.paths:
        if TMP_DIR.match(path):
            return TMP_MESSAGE
    return None


# The policy. `doc` is rendered by --explain and asserted against CLAUDE.md,
# so every rule documents itself exactly once.
RULES = (
    (
        "bazel-clean",
        "`bazelisk clean` and `bazel clean` are blocked.",
        check_bazel_clean,
    ),
    (
        "git-local-branch",
        "Git operations (`checkout`, `switch`, `rebase`, `cherry-pick`, `merge`, "
        "`reset`, `pull`) on local `master` or `main` branches are blocked. Use "
        "remote-tracking branches or detached HEADs instead.",
        check_git_local_branch,
    ),
    (
        "spelunking",
        "Spelunking in `bazel-*` output directories and `.cache` using native "
        "tools (`grep`, `find`, `cat`) or agent file-reading tools is blocked to "
        "prevent context explosion.",
        check_spelunking,
    ),
    (
        "tmp",
        "The use of the global `/tmp` directory is blocked. Always use a local "
        "`./tmp` directory for scratch work.",
        check_tmp,
    ),
)


class Request:
    """A hook request, normalized across dialects."""

    def __init__(self, dialect, command, paths):
        self.dialect = dialect
        self.command = command
        self.paths = paths


def parse(payload):
    """Normalize a Claude Code or antigravity payload into a Request."""
    if "toolCall" in payload:
        dialect = "antigravity"
        args = payload.get("toolCall", {}).get("args", {}) or {}
    else:
        dialect = "claude"
        args = payload.get("tool_input", {}) or {}

    command = ""
    for key in COMMAND_KEYS:
        if args.get(key):
            command = str(args[key])
            break

    paths = []
    # The working directory is a path for policy purposes: a command that runs
    # *inside* a forbidden directory needs no forbidden argument.
    for key in CWD_KEYS + PATH_KEYS:
        value = args.get(key)
        if value:
            paths.append(str(value))

    return Request(dialect, command, paths)


def decide(request):
    """Return a deny reason, or None to let the normal permission flow run."""
    for _, _, check in RULES:
        reason = check(request)
        if reason:
            return reason
    return None


def respond(dialect, reason):
    """Serialize the verdict in the caller's dialect."""
    if reason is None:
        # Claude Code: silence means "no opinion". Saying "allow" would bypass
        # the user's own permission prompts for every tool call.
        if dialect == "antigravity":
            print(json.dumps({"decision": "allow"}))
        return
    if dialect == "antigravity":
        print(json.dumps({"decision": "deny", "reason": reason}))
    else:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )


def explain():
    """Render the policy as the markdown bullet list CLAUDE.md must contain."""
    return "\n".join("- " + doc for _, doc, _ in RULES)


def main():
    if "--explain" in sys.argv[1:]:
        print(explain())
        return

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            respond("claude", None)
            return
        request = parse(json.loads(raw))
        respond(request.dialect, decide(request))
    except Exception:  # pragma: no cover - failsafe, never break the agent
        respond("claude", None)


if __name__ == "__main__":
    main()
