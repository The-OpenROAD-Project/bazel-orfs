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
        action=argparse.BooleanOptionalAction,
        help="Check pre-conditions for bloop to work.",
    )
    parser.add_argument("--directory", nargs=1, default=[])
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    workspace = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])

    if args.check_bloop:
        # Upon major java version upgrades, bloop and vscode does not
        # take kindly to files being changed undeneath them.
        #
        # The symptom are inscrutible errors and little help from ChatGPT
        # or Google.
        ok = True
        for cmd, info in (
            (("-x", "code"), "Visual Studio Code"),
            (("-f", "BloopServer"), "Bloop"),
        ):
            try:
                subprocess.check_output(["pgrep"] + list(cmd))
                print(f"Error: run `pkill {' '.join(cmd)}`, {info} is running.")
                ok = False
            except subprocess.CalledProcessError as e:
                if e.returncode != 1:
                    # 1 means "not found", anything else is an actual error
                    raise
        if not ok:
            sys.exit(1)

        for root, dirs, files in os.walk(workspace):
            forbidden = {".bloop", ".metals", ".bazelbsp", ".bsp"} & set(dirs)
            for folder in forbidden:
                folder_path = os.path.join(root, folder)
                print(f"Cleaning up (removing), removing: {folder_path}")
                shutil.rmtree(folder_path)
            forbidden_files = {".bazelproject"} & set(files)
            for file in forbidden_files:
                file_path = os.path.join(root, file)
                print(f"Cleaning up (removing), removing: {file_path}")
                os.remove(file_path)

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
            # Avoid ephemeral symlinks, resolve to real path
            src = os.path.realpath(src)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(src, dst)


if __name__ == "__main__":
    main()
