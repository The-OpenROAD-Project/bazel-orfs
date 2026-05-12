"""Entry point for orfs_run_executable.

The rule's shell wrapper sets ORFS_MAKE_EXE / ORFS_MAKEFILE / ORFS_CMD in
the environment and prepends the BUILD-time `arguments` dict to argv as
positional KEY=VALUE tokens. User-supplied `bazelisk run -- ...` args are
appended after, so make's last-wins rule gives them priority over the
BUILD-time defaults.

Make-level variable overrides (KEY=VALUE on the make command line) become
environment variables when make invokes the recipe — that's how the Tcl
script sees the user's TO_GLOB / OUTPUT etc.
"""

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an ORFS Tcl script with runtime arguments.",
        epilog=(
            "Positional KEY=VALUE pairs become make variable overrides and "
            "environment variables for the Tcl script. CLI args override "
            "the BUILD-time `arguments` dict (make last-wins)."
        ),
    )
    parser.add_argument(
        "--cmd",
        default=None,
        help="Override the make target (default: the rule's `cmd` attr).",
    )
    parser.add_argument(
        "overrides",
        nargs="*",
        metavar="KEY=VALUE",
        help="make variable overrides; later values win.",
    )
    args = parser.parse_args()

    try:
        make = os.environ["ORFS_MAKE_EXE"]
        makefile = os.environ["ORFS_MAKEFILE"]
    except KeyError as exc:
        sys.exit(
            f"{sys.argv[0]}: missing env var {exc.args[0]} — "
            "was this invoked outside the orfs_run_executable wrapper?"
        )

    cmd = args.cmd if args.cmd is not None else os.environ.get("ORFS_CMD", "run")

    argv = [make, "--file", makefile, *args.overrides, cmd]
    os.execvp(make, argv)


if __name__ == "__main__":
    main()
