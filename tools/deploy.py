#! /bin/env python3

import argparse
import os
import sys
import json
import subprocess
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description="Deploy external headers for compile commands.",
        fromfile_prefix_chars="@",
    )
    parser.add_argument("--manifest")
    parser.add_argument(
        "--check-bloop",
        action="store_true",
        default=False,
        help="Check pre-conditions for bloop to work.",
    )
    parser.add_argument("--directory", nargs=1, default=[])
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    workspace = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])

    if args.check_bloop:
        try:
            subprocess.check_output(["pgrep", "-x", "code"])
            print(
                "Error: 'code' process is running. Please close it before proceeding."
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                # 1 means "not found", anything else is an actual error
                raise

        for root, dirs, files in os.walk(workspace):
            forbidden = {".bloop", ".metals", ".bazelbsp"} & set(dirs)
            for folder in forbidden:
                folder_path = os.path.join(root, folder)
                print(f"Cleaning up (removing), removing: {folder_path}")
                shutil.rmtree(folder_path)

    execroot = os.readlink(
        os.path.join(workspace, "bazel-" + os.path.basename(workspace))
    )

    for path in args.paths:
        dst = os.path.join(workspace, *args.directory, os.path.basename(path))
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        with open(path, "r") as input, open(dst, "w") as output:
            output.write(input.read().replace("__EXEC_ROOT__", str(workspace)))

    with open(args.manifest, "r") as input:
        for path in json.load(input):
            dst = os.path.join(workspace, path)
            if os.path.exists(dst):
                os.remove(dst)

            src = os.path.join(execroot, path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(src, dst)


if __name__ == "__main__":
    main()
