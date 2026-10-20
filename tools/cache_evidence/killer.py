"""Kill every process a sandboxed Bazel action starts, while a build runs.

A remote cache hit never starts a process; a miss is spawned sandboxed
and dies before it computes anything, so the build learns what the cache
has without running what it has not. Used by cache_evidence.py's capture
and by //:export --cached-only.
"""

import os
import signal
import threading


def sandboxed_pids(root, proc="/proc", self_pid=None):
    """Processes running inside a sandbox under root: their working
    directory is there (an action's own process, or an orphan it left),
    or their command line names it (Bazel's wrapper around the action)."""
    self_pid = os.getpid() if self_pid is None else self_pid
    found = []
    for name in os.listdir(proc):
        if not name.isdigit() or int(name) == self_pid:
            continue
        try:
            with open(os.path.join(proc, name, "cmdline"), "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
            cwd = os.readlink(os.path.join(proc, name, "cwd"))
        except OSError:
            continue
        if root in cmd or cwd.startswith(root):
            found.append(int(name))
    return found


class Killer(threading.Thread):
    """Kills every process a sandboxed action starts, for as long as the
    build runs. A remote cache hit never starts one; a miss dies before it
    computes anything, and Bazel logs it, with its inputs, as failed."""

    def __init__(self, output_base, period=0.05):
        threading.Thread.__init__(self)
        self.daemon = True
        self.root = os.path.join(output_base, "sandbox") + os.sep
        self.period = period
        self.killed = set()
        self.done = threading.Event()

    def run(self):
        while not self.done.is_set():
            for pid in sandboxed_pids(self.root):
                try:
                    os.kill(pid, signal.SIGKILL)
                    self.killed.add(pid)
                except OSError:
                    pass
            self.done.wait(self.period)

    def stop(self):
        self.done.set()
        self.join()
