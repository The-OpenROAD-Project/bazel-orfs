#!/usr/bin/env python3
"""The watchdog runs while an arm is already going wrong.

Which is the whole difficulty: every path through it has to survive a
process that exits between two reads of /proc, a gdb that is not
installed, and a torn read that produces a cycle. A second failure
inside the hang handler loses the only record of the hang.

The process-tree logic is pure and tested directly; /proc is faked as a
directory so `read_ppids` and `process_name` are tested against the
real parser rather than a mock of it.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import watchdog


def fake_proc(root, procs):
    """procs: {pid: (ppid, comm)} -> a directory shaped like /proc."""
    for pid, (ppid, comm) in procs.items():
        path = os.path.join(root, str(pid))
        os.makedirs(path)
        # The real format, including a comm with a space and a paren in
        # it, which is why the parser splits on the last ')'.
        with open(os.path.join(path, "stat"), "w") as handle:
            handle.write("{} ({}) S {} 1 1 0 -1 0\n".format(pid, comm, ppid))
        with open(os.path.join(path, "comm"), "w") as handle:
            handle.write(comm + "\n")
    # /proc holds non-numeric entries too.
    os.makedirs(os.path.join(root, "self"), exist_ok=True)
    return root


class Tree(unittest.TestCase):
    def test_descendants_are_found_through_intermediate_shells(self):
        # The real shape: make -> sh wrapper -> openroad.
        ppids = {100: 1, 200: 100, 300: 200, 999: 1}
        self.assertEqual(watchdog.descendants(100, ppids), [200, 300])

    def test_an_unrelated_tree_is_not_included(self):
        ppids = {100: 1, 200: 100, 400: 1, 500: 400}
        self.assertEqual(watchdog.descendants(100, ppids), [200])

    def test_a_torn_read_that_produces_a_cycle_terminates(self):
        # Cannot happen in a real tree; can happen in a /proc snapshot.
        # Looping forever inside the hang handler would be a poor way
        # to report a hang.
        ppids = {100: 200, 200: 100}
        self.assertEqual(watchdog.descendants(100, ppids), [200])

    def test_a_leaf_has_no_descendants(self):
        self.assertEqual(watchdog.descendants(300, {300: 200}), [])


class Proc(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def test_ppids_are_parsed_past_a_comm_containing_parens(self):
        fake_proc(self.root, {100: (1, "make"), 200: (100, "open(road)")})
        self.assertEqual(watchdog.read_ppids(self.root), {100: 1, 200: 100})

    def test_a_process_that_exits_mid_read_is_skipped_not_an_error(self):
        fake_proc(self.root, {100: (1, "make")})
        os.makedirs(os.path.join(self.root, "404"))  # no stat file
        self.assertEqual(watchdog.read_ppids(self.root), {100: 1})

    def test_only_the_tool_processes_are_selected(self):
        fake_proc(
            self.root,
            {
                100: (1, "make"),
                200: (100, "sh"),
                300: (200, "openroad"),
                400: (200, "opensta"),
            },
        )
        self.assertEqual(
            watchdog.tools_under(100, self.root), [(300, "openroad"), (400, "opensta")]
        )

    def test_the_make_and_shell_above_the_tool_are_not_dumped(self):
        # They are parked in wait() and say nothing about the hang.
        fake_proc(self.root, {100: (1, "make"), 200: (100, "bash")})
        self.assertEqual(watchdog.tools_under(100, self.root), [])


class Capture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.dest = os.path.join(self.root, "stacks.txt")

    def _proc(self):
        proc = os.path.join(self.root, "proc")
        os.makedirs(proc)
        return fake_proc(proc, {100: (1, "make"), 300: (100, "openroad")})

    def test_a_backtrace_is_written_per_tool_process(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            if argv[:2] == ["gdb", "--version"]:
                return subprocess.CompletedProcess(argv, 0, "GNU gdb", "")
            return subprocess.CompletedProcess(argv, 0, "Thread 1 parked in futex", "")

        got = watchdog.capture(100, self.dest, self._proc(), runner)
        self.assertEqual(got, self.dest)
        with open(self.dest) as handle:
            text = handle.read()
        self.assertIn("pid 300 (openroad)", text)
        self.assertIn("futex", text)
        self.assertIn(["gdb", "-p", "300", "--batch", "-ex", "thread apply all bt"], calls)

    def test_no_gdb_falls_back_to_abort_and_says_so(self):
        signalled = []

        def runner(argv, **kwargs):
            raise OSError("no gdb")

        original = watchdog.os.kill
        watchdog.os.kill = lambda pid, sig: signalled.append((pid, sig))
        self.addCleanup(setattr, watchdog.os, "kill", original)

        got = watchdog.capture(100, self.dest, self._proc(), runner)
        self.assertEqual(got, self.dest)
        with open(self.dest) as handle:
            text = handle.read()
        self.assertIn("gdb is not installed", text)
        self.assertEqual([pid for pid, _ in signalled], [300])

    def test_a_gdb_that_fails_is_recorded_rather_than_raised(self):
        def runner(argv, **kwargs):
            if argv[:2] == ["gdb", "--version"]:
                return subprocess.CompletedProcess(argv, 0, "", "")
            raise subprocess.TimeoutExpired(argv, 1)

        got = watchdog.capture(100, self.dest, self._proc(), runner)
        self.assertEqual(got, self.dest)
        with open(self.dest) as handle:
            self.assertIn("gdb failed", handle.read())

    def test_no_tool_process_writes_nothing_and_returns_none(self):
        proc = os.path.join(self.root, "proc")
        os.makedirs(proc)
        fake_proc(proc, {100: (1, "make")})
        self.assertIsNone(watchdog.capture(100, self.dest, proc, lambda *a, **k: None))
        self.assertFalse(os.path.exists(self.dest))


if __name__ == "__main__":
    unittest.main()
