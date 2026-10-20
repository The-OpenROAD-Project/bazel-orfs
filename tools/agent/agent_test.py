#!/usr/bin/env python3
"""What @bazel-orfs//:agent does to a workspace, and what it exports."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import agent

SKILLS_DIR = os.path.join(
    os.environ.get("TEST_SRCDIR", ""),
    os.environ.get("TEST_WORKSPACE", "_main"),
    ".claude",
    "skills",
)


def _fake_root(base):
    root = os.path.join(base, "bazel-orfs")
    for s in agent.EXPORTED_SKILLS:
        d = os.path.join(root, ".claude", "skills", s)
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("---\nname: %s\n---\n" % s)
    return root


def _no_git(*args, **kwargs):
    raise OSError("no git")


class ExportedSkills(unittest.TestCase):
    """The skills themselves, as bazel-orfs ships them."""

    def test_every_skill_is_exported_or_internal(self):
        on_disk = set(os.listdir(SKILLS_DIR))
        exported = set(agent.EXPORTED_SKILLS)
        internal = set(agent.INTERNAL_SKILLS)
        self.assertFalse(exported & internal)
        self.assertEqual(on_disk, exported | internal)

    def test_exported_skill_reads_anywhere(self):
        for s in agent.EXPORTED_SKILLS:
            with open(os.path.join(SKILLS_DIR, s, "SKILL.md")) as f:
                text = f.read()
            with self.subTest(skill=s):
                self.assertRegex(text, r"\A---\nname: %s\n" % re.escape(s))
                # A link is seen from the workspace's .claude/skills/<s>,
                # so nothing may lead out of the skill directory.
                self.assertNotIn("](../", text)
                self.assertNotIn(".claude/commands/", text)
                # bazel-orfs's targets by the name that resolves everywhere.
                self.assertIsNone(
                    re.search(r"(^|[^@\w./-])//(:deps|tools/)", text, re.M)
                )


class Sync(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.root = _fake_root(self.base)
        self.ws = os.path.join(self.base, "chip")
        os.makedirs(self.ws)

    def tearDown(self):
        shutil.rmtree(self.base)

    def test_links_and_is_idempotent(self):
        _, changed = agent.sync(self.ws, self.root, _no_git)
        self.assertTrue(changed)
        self.assertEqual(
            os.path.realpath(os.path.join(self.ws, ".claude", "bazel-orfs")),
            os.path.realpath(self.root),
        )
        for s in agent.EXPORTED_SKILLS:
            path = os.path.join(self.ws, ".claude", "skills", s)
            self.assertEqual(
                os.readlink(path),
                os.path.join("..", "bazel-orfs", ".claude", "skills", s),
            )
            self.assertTrue(os.path.isfile(os.path.join(path, "SKILL.md")))
        _, changed = agent.sync(self.ws, self.root, _no_git)
        self.assertFalse(changed)

    def test_follows_a_moved_root(self):
        agent.sync(self.ws, self.root, _no_git)
        moved = os.path.join(self.base, "moved")
        shutil.copytree(self.root, moved)
        _, changed = agent.sync(self.ws, moved, _no_git)
        self.assertTrue(changed)
        self.assertEqual(
            os.readlink(os.path.join(self.ws, ".claude", "bazel-orfs")), moved
        )

    def test_drops_a_skill_no_longer_exported_and_keeps_others(self):
        skills = os.path.join(self.ws, ".claude", "skills")
        os.makedirs(os.path.join(skills, "mine"))
        os.makedirs(skills, exist_ok=True)
        os.symlink(
            os.path.join("..", "bazel-orfs", ".claude", "skills", "gone"),
            os.path.join(skills, "gone"),
        )
        agent.sync(self.ws, self.root, _no_git)
        self.assertFalse(os.path.lexists(os.path.join(skills, "gone")))
        self.assertTrue(os.path.isdir(os.path.join(skills, "mine")))

    def test_refuses_a_workspace_skill_of_the_same_name(self):
        os.makedirs(os.path.join(self.ws, ".claude", "skills", "dirty-lane"))
        with self.assertRaisesRegex(agent.Refused, "dirty-lane"):
            agent.sync(self.ws, self.root, _no_git)
        self.assertFalse(
            os.path.lexists(os.path.join(self.ws, ".claude", "bazel-orfs"))
        )

    def test_refuses_a_directory_in_place_of_the_link(self):
        os.makedirs(os.path.join(self.ws, ".claude", "bazel-orfs"))
        with self.assertRaisesRegex(agent.Refused, "in the way"):
            agent.sync(self.ws, self.root, _no_git)

    def test_refuses_bazel_orfs_itself(self):
        with self.assertRaisesRegex(agent.Refused, "bazel-orfs itself"):
            agent.sync(self.root, self.root, _no_git)

    def test_refuses_a_root_without_an_exported_skill(self):
        shutil.rmtree(os.path.join(self.root, ".claude", "skills", "dirty-lane"))
        with self.assertRaisesRegex(agent.Refused, "dirty-lane"):
            agent.sync(self.ws, self.root, _no_git)

    def test_keeps_the_links_out_of_git(self):
        if shutil.which("git") is None:
            self.skipTest("no git")
        subprocess.check_call(["git", "init", "-q", self.ws])
        exclude = os.path.join(self.ws, ".git", "info", "exclude")
        with open(exclude, "a") as f:
            f.write("mine\n")
        agent.sync(self.ws, self.root)
        agent.sync(self.ws, self.root)
        with open(exclude) as f:
            text = f.read()
        self.assertIn("mine\n", text)
        self.assertEqual(text.count(agent.EXCLUDE_BEGIN), 1)
        self.assertIn("/.claude/bazel-orfs\n", text)
        self.assertIn("/.claude/skills/dirty-lane\n", text)
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=self.ws,
            universal_newlines=True,
        )
        self.assertEqual(status, "")

    def _share_skills(self):
        """.claude/skills as a link to a skills directory other agents share."""
        os.makedirs(os.path.join(self.ws, ".shared", "mine"))
        os.makedirs(os.path.join(self.ws, ".claude"))
        os.symlink(
            os.path.join("..", ".shared"), os.path.join(self.ws, ".claude", "skills")
        )

    def test_links_into_a_shared_skills_directory(self):
        self._share_skills()
        paths, _ = agent.sync(self.ws, self.root, _no_git)
        for s in agent.EXPORTED_SKILLS:
            path = os.path.join(self.ws, ".shared", s)
            self.assertEqual(
                os.readlink(path),
                os.path.join("..", ".claude", "bazel-orfs", ".claude", "skills", s),
            )
            self.assertTrue(
                os.path.isfile(
                    os.path.join(self.ws, ".claude", "skills", s, "SKILL.md")
                )
            )
        self.assertIn(os.path.join(".shared", "dirty-lane"), paths)
        self.assertTrue(os.path.isdir(os.path.join(self.ws, ".shared", "mine")))
        _, changed = agent.sync(self.ws, self.root, _no_git)
        self.assertFalse(changed)

    def test_keeps_links_in_a_shared_skills_directory_out_of_git(self):
        if shutil.which("git") is None:
            self.skipTest("no git")
        self._share_skills()
        subprocess.check_call(["git", "init", "-q", self.ws])
        with open(os.path.join(self.ws, ".shared", "mine", "SKILL.md"), "w") as f:
            f.write("mine\n")
        subprocess.check_call(["git", "add", "-A"], cwd=self.ws)
        agent.sync(self.ws, self.root)
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=self.ws,
            universal_newlines=True,
        )
        self.assertEqual(
            sorted(line[3:] for line in status.splitlines()),
            [".claude/skills", ".shared/mine/SKILL.md"],
        )

    def test_refuses_a_skills_directory_outside_the_workspace(self):
        os.makedirs(os.path.join(self.ws, ".claude"))
        os.symlink(self.base, os.path.join(self.ws, ".claude", "skills"))
        with self.assertRaisesRegex(agent.Refused, "outside the workspace"):
            agent.sync(self.ws, self.root, _no_git)


class Setup(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.ws)

    def _json(self, *path):
        with open(os.path.join(self.ws, *path)) as f:
            return json.load(f)

    def _write(self, data, *path):
        os.makedirs(os.path.join(self.ws, *path[:-1]), exist_ok=True)
        with open(os.path.join(self.ws, *path), "w") as f:
            json.dump(data, f)

    def test_mcp_keeps_other_servers(self):
        self._write({"mcpServers": {"other": {"command": "x"}}}, ".mcp.json")
        self.assertTrue(agent.setup_mcp(self.ws))
        self.assertFalse(agent.setup_mcp(self.ws))
        servers = self._json(".mcp.json")["mcpServers"]
        self.assertEqual(servers["other"], {"command": "x"})
        self.assertEqual(servers["odb-debug"], agent.MCP_ENTRY)

    def test_mcp_refuses_a_different_odb_debug(self):
        self._write({"mcpServers": {"odb-debug": {"command": "mine"}}}, ".mcp.json")
        with self.assertRaisesRegex(agent.Refused, "odb-debug"):
            agent.setup_mcp(self.ws)

    def test_hook_keeps_other_settings(self):
        mine = {"matcher": "startup", "hooks": [{"type": "command", "command": "x"}]}
        self._write(
            {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [mine]}},
            ".claude",
            "settings.json",
        )
        self.assertTrue(agent.setup_hook(self.ws))
        self.assertFalse(agent.setup_hook(self.ws))
        data = self._json(".claude", "settings.json")
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(data["hooks"]["SessionStart"], [mine, agent.HOOK])

    def test_rules_import_appended_once(self):
        with open(os.path.join(self.ws, "CLAUDE.md"), "w") as f:
            f.write("# chip\n")
        self.assertTrue(agent.setup_rules(self.ws))
        self.assertFalse(agent.setup_rules(self.ws))
        with open(os.path.join(self.ws, "CLAUDE.md")) as f:
            text = f.read()
        self.assertTrue(text.startswith("# chip\n"))
        self.assertEqual(text.split("\n").count(agent.RULES_IMPORT), 1)

    def test_rules_import_creates_claude_md(self):
        self.assertTrue(agent.setup_rules(self.ws))
        with open(os.path.join(self.ws, "CLAUDE.md")) as f:
            self.assertIn(agent.RULES_IMPORT, f.read())


if __name__ == "__main__":
    unittest.main()
