#! /bin/env python3

import argparse
import os
import sys
import json
import subprocess
import shutil
from pathlib import Path

import re


def parse_bazel_project(file_path):
    project_data = {}
    current_section = None

    with open(file_path, "r") as f:
        for line in f:
            # 1. Clean up the line
            line = line.split("#")[
                0
            ].rstrip()  # Remove comments and trailing whitespace
            if not line.strip():
                continue

            # 2. Check for section headers (e.g., "directories:")
            if line.endswith(":"):
                current_section = line[:-1].strip()
                project_data[current_section] = []

            # 3. Handle indented entries
            elif line.startswith("  "):
                if current_section:
                    project_data[current_section].append(line.strip())

            # 4. Handle top-level directives (like imports)
            else:
                directive_parts = line.split(maxsplit=1)
                if len(directive_parts) == 2:
                    key, value = directive_parts
                    project_data.setdefault(key, []).append(value)

    return project_data


def main():
    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description="Set up BSP.",
    )
    parser.parse_args()

    # # dump all env vars
    # for k, v in os.environ.items():
    #     print(f"{k}={v}")

    workspace = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])

    if not (workspace / ".bazelproject").exists():
        print("Error: .bazelproject file not found in workspace root.")
        exit(1)

    data = parse_bazel_project(workspace / ".bazelproject")
    print("Targets found: " + str(data.get("targets", [])))
    for target in data.get("targets", []):
        print(f" - {target}")

    print("Checking enabled rules:")
    required_rules = ("rules_scala", "rules_jvm", "rules_java")
    rules = data.get("enabled_rules", [])
    for rule in required_rules:
        if rule in rules:
            print(f" - {rule} enabled")
        else:
            print(f"Error: {rule} is missing")
            exit(1)

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
            print(f"Rleaning up (removing): {folder_path}")
            shutil.rmtree(folder_path)

    cmd = ["bazelisk", "build"] + data.get("targets", [])
    print("Running: " + subprocess.list2cmdline(cmd))
    subprocess.run(cmd, check=True, cwd=workspace)


if __name__ == "__main__":
    main()
