"""Does CI's test set build only what it has to?

    bazelisk run //local:check-ci-clean

CI has 30 minutes on a 4-core runner, and what fits in them is set by
what `bazelisk test ...` compiles. Turnaround is not a convenience: a
human waits on it, and an AI agent working on this repository is limited
by it far more, because what an agent gets done is the number of
decisions it can make per hour, and each one waits on a result.

Each check below named a cost that had crept in unnoticed, and costs
creep back the same way; run this after changing what a test depends on.
It reads the configured graph (query and cquery), so it takes a minute
and builds nothing.

- OpenROAD and yosys only in the exec configuration the flow stages use.
  A test that lists `@openroad` or `@yosys` in its data compiles either a
  second time, with everything it links: list //test:openroad_exec or
  //test:yosys_exec (test/exec_tool.bzl).
- No iverilog. It is a dev dependency for local studies (//test:local).
"""

import os
import shutil
import subprocess
import sys

TESTS = 'tests(//...) except attr(tags, "manual", tests(//...))'


def bazel(ws, *args):
    exe = shutil.which("bazelisk") or "bazel"
    r = subprocess.run(
        [exe] + list(args),
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit("{} {} failed".format(exe, args[0]))
    return [line for line in r.stdout.splitlines() if line]


def main():
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    # @openroad's own tests come in through manual test_suites; CI runs
    # only this repository's.
    tests = [t for t in bazel(ws, "query", TESTS) if t.startswith("//")]
    universe = "set({})".format(" ".join(tests))

    checks = []
    for tool in ("@openroad//:openroad", "@yosys//:yosys"):
        checks.append(
            (
                "{} only in the exec configuration".format(tool),
                "{} built in the target configuration for".format(tool),
                bazel(
                    ws,
                    "cquery",
                    "rdeps({}, config({}, target), 1)".format(universe, tool),
                ),
            )
        )
    checks.append(
        (
            "no iverilog",
            "iverilog built for",
            bazel(ws, "cquery", "rdeps({}, @iverilog//:iverilog, 1)".format(universe)),
        )
    )

    failed = False
    for ok, fail, found in checks:
        if found:
            failed = True
            print("FAIL: {}:".format(fail))
            for line in found:
                print("  " + line)
        else:
            print("ok:   " + ok)
    print("{} tests checked".format(len(tests)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
