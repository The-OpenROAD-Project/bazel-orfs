#!/usr/bin/env python3
"""Tests for the shared PreToolUse guard.

Every policy case is expressed once, in a dialect-neutral form, and then run
through *both* hook dialects. That is the point of the table: a rule cannot be
enforced for Claude Code but silently missing for antigravity (or vice versa),
which is exactly how the two drifted apart before they shared this script.
"""

import json
import os
import subprocess
import sys
import unittest

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_tool.py")

# (field, value, expected) — expected is None for "allowed", otherwise a
# substring the deny reason must contain.
#
# field is dialect-neutral:
#   "command" — the shell command line
#   "path"    — a file/directory argument of a read/write/search tool
#   "cwd"     — the working directory of a shell command
CASES = [
    # --- bazel clean -----------------------------------------------------
    ("command", "bazel clean", "protects bazel cache"),
    ("command", "bazelisk clean --expunge", "protects bazel cache"),
    ("command", "bazel --noblock_for_lock clean", "protects bazel cache"),
    ("command", "/usr/bin/bazel clean", "protects bazel cache"),
    ("command", "USE_BAZEL_VERSION=7.0.0 bazelisk clean", "protects bazel cache"),
    ("command", "bazel-7.4.0 clean", "protects bazel cache"),
    ("command", "cd sub && bazel clean", "protects bazel cache"),
    ("command", "bazel build //...", None),
    ("command", "bazelisk test //:fix_lint_test", None),
    # The repository is *named* bazel-orfs; that is not a bazel invocation.
    ("command", "bazel-orfs clean", None),
    ("command", "git commit -m 'clean up bazel invocation'", None),
    # --- local main/master ----------------------------------------------
    ("command", "git checkout main", "verboten"),
    ("command", "git switch master", "verboten"),
    ("command", "git rebase main", "verboten"),
    ("command", "git reset --hard master", "verboten"),
    ("command", "git cherry-pick main", "verboten"),
    ("command", "git merge main", "verboten"),
    ("command", "git pull origin main", "verboten"),
    ("command", "git checkout origin/main", None),
    ("command", "git rebase upstream/master", None),
    ("command", "git log origin/main", None),
    ("command", "git checkout -b feature-x", None),
    ("command", "git checkout mainline", None),
    ("command", "git merge --abort", None),
    # --- spelunking ------------------------------------------------------
    ("command", "grep -rn foo bazel-out/k8-fastbuild", "context explosion"),
    ("command", "cat bazel-testlogs/x/test.log", "bazel-testlogs"),
    ("command", "ls ~/.cache/bazel", "bazel cache"),
    ("command", "grep foo src/*.py", None),
    ("command", "ls bazel-orfs", None),
    ("path", "bazel-out/k8-fastbuild/bin/x", "context explosion"),
    ("path", "bazel-bin/design.v", "bazel-bin"),
    ("path", "/home/u/.cache/bazel/x/y", "bazel cache"),
    ("path", "/home/u/bazel-orfs/BUILD", None),
    ("path", "src/main.py", None),
    ("cwd", "bazel-out", "context explosion"),
    ("cwd", "/home/u/bazel-orfs", None),
    # --- prose is not code ----------------------------------------------
    # Writing *about* a forbidden command must stay possible; a guard that
    # blocks its own commit messages and documentation is unusable.
    ("command", "git commit -m 'do not run bazel clean, it wipes the cache'", None),
    ("command", "git commit -m \"blocked: git checkout main\"", None),
    ("command", "echo 'grep -rn foo bazel-out/x is forbidden'", None),
    ("command", "echo \"scratch goes in ./tmp, never /tmp\"", None),
    # ... but a quoted single argument is still an argument.
    ("command", "grep -rn foo \"bazel-out/k8-fastbuild\"", "context explosion"),
    ("command", 'git checkout "main"', "verboten"),
    ("command", 'cat "/tmp/x"', "./tmp"),
    ("command", "cat <<'EOF' > note.md\nnever run bazel clean\nEOF", None),
    # --- /tmp ------------------------------------------------------------
    ("command", "mkdir -p /tmp/scratch", "./tmp"),
    ("command", "python3 run.py --out /tmp/x.json", "./tmp"),
    ("command", "mkdir -p ./tmp/scratch", None),
    ("command", "cat ./tmp/notes.txt", None),
    ("path", "/tmp/scratch/x", "./tmp"),
    ("path", "./tmp/scratch/x", None),
    ("path", "/var/tmp/x", None),
    ("cwd", "/tmp", "./tmp"),
]

# How each neutral field is spelled in each dialect. A field absent from a
# dialect (Claude Code's Bash tool has no cwd argument) is skipped there.
CLAUDE_PAYLOAD = {
    "command": lambda v: {"tool_name": "Bash", "tool_input": {"command": v}},
    "path": lambda v: {"tool_name": "Read", "tool_input": {"file_path": v}},
}
ANTIGRAVITY_PAYLOAD = {
    "command": lambda v: {
        "toolCall": {"name": "run_command", "args": {"CommandLine": v}}
    },
    "path": lambda v: {
        "toolCall": {"name": "view_file", "args": {"AbsolutePath": v}}
    },
    "cwd": lambda v: {"toolCall": {"name": "run_command", "args": {"Cwd": v}}},
}


def run_guard(payload):
    """Run the hook exactly as an agent would, returning its stdout."""
    result = subprocess.run(
        [sys.executable, GUARD],
        input="" if payload is None else json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def claude_reason(stdout):
    """Extract the deny reason from a Claude Code response, or None."""
    if not stdout:
        return None
    output = json.loads(stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse", output
    if output["permissionDecision"] != "deny":
        return None
    return output["permissionDecisionReason"]


def antigravity_reason(stdout):
    """Extract the deny reason from an antigravity response, or None."""
    response = json.loads(stdout)
    if response["decision"] != "deny":
        return None
    return response["reason"]


class PolicyTest(unittest.TestCase):
    def check(self, dialect, builders, extract, field, value, expected):
        if field not in builders:
            return
        stdout = run_guard(builders[field](value))
        reason = extract(stdout)
        if expected is None:
            self.assertIsNone(
                reason, f"{dialect}: {field}={value!r} should be allowed"
            )
        else:
            self.assertIsNotNone(
                reason, f"{dialect}: {field}={value!r} should be denied"
            )
            self.assertIn(expected, reason, f"{dialect}: {field}={value!r}")

    def test_claude_dialect(self):
        for field, value, expected in CASES:
            with self.subTest(field=field, value=value):
                self.check(
                    "claude",
                    CLAUDE_PAYLOAD,
                    claude_reason,
                    field,
                    value,
                    expected,
                )

    def test_antigravity_dialect(self):
        for field, value, expected in CASES:
            with self.subTest(field=field, value=value):
                self.check(
                    "antigravity",
                    ANTIGRAVITY_PAYLOAD,
                    antigravity_reason,
                    field,
                    value,
                    expected,
                )


class ProtocolTest(unittest.TestCase):
    def test_claude_pass_is_silence_not_allow(self):
        # permissionDecision "allow" would bypass the user's own permission
        # prompts for every tool call, so a pass must produce no output.
        self.assertEqual(
            run_guard({"tool_name": "Bash", "tool_input": {"command": "ls"}}), ""
        )

    def test_antigravity_pass_is_explicit_allow(self):
        stdout = run_guard(
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}}}
        )
        self.assertEqual(json.loads(stdout), {"decision": "allow"})

    def test_empty_stdin_is_silent(self):
        self.assertEqual(run_guard(None), "")

    def test_unknown_tool_without_arguments_is_allowed(self):
        self.assertEqual(run_guard({"tool_name": "TodoWrite", "tool_input": {}}), "")

    def test_malformed_input_fails_open(self):
        result = subprocess.run(
            [sys.executable, GUARD],
            input="{not json",
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "")


class ExplainTest(unittest.TestCase):
    def test_explain_lists_every_rule(self):
        result = subprocess.run(
            [sys.executable, GUARD, "--explain"],
            capture_output=True,
            text=True,
            check=True,
        )
        bullets = [
            line for line in result.stdout.splitlines() if line.startswith("- ")
        ]
        self.assertEqual(len(bullets), len(result.stdout.strip().splitlines()))
        self.assertTrue(bullets)


if __name__ == "__main__":
    unittest.main()
