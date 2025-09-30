#! /bin/env python3

import argparse
import copy
import json
import os
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

PATHS_TO_REWRITE = ["bazel", "external", "third_party"]


def rewrite_bloop(data: Dict[str, Any],
                  dest_root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:

    project = data["project"]
    classpaths = project["classpath"]
    modules = project["resolution"]["modules"]
    scala_jars = project["scala"]["jars"]

    base = os.getcwd()

    copies = {}

    resolved = dest_root.resolve()

    next_classpaths = []
    for classpath in classpaths:
        full = Path(classpath)
        shaved = full.relative_to(base).as_posix()

        new_path = resolved / shaved

        copies[str(classpath)] = str(new_path)
        next_classpaths.append(new_path)

    project["classpath"] = next_classpaths
    next_modules = copy.deepcopy(modules)

    for module in next_modules:
        next_artifacts = copy.deepcopy(module["artifacts"])
        for artifact in next_artifacts:
            full = Path(artifact["path"])
            shaved = full.relative_to(base).as_posix()

            new_path = resolved / shaved

            artifact["path"] = dest_root / Path(new_path)

            copies[str(full)] = str(artifact["path"])

        module["artifacts"] = next_artifacts

    project["resolution"]["modules"] = next_modules

    next_jars = []
    for jar in scala_jars:
        full = Path(jar)
        shaved = full.relative_to(base).as_posix()

        new_path = resolved / shaved

        copies[str(jar)] = str(new_path)

        jar = dest_root / Path(new_path)
        next_jars.append(jar)

    project["scala"]["jars"] = next_jars
    data["project"] = project

    # print(data)

    return copies, data


# Assumes we're in ascenium root
def process_bloop_artifacts(lsp_files_destination: Path):
    workspace = Path(os.getcwd())
    blooplib_path = workspace / ".bloop" / "blooplib.json"
    tilelink_path = workspace / ".bloop" / "tilelink.json"
    hardfloat_path = workspace / ".bloop" / "hardfloat.json"

    copies = {}

    input_paths = [blooplib_path, tilelink_path, hardfloat_path]
    for input_path in input_paths:
        try:
            data = json.loads(input_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERROR: failed to parse JSON: {e}", file=sys.stderr)
            sys.exit(2)

        dest_root = Path(lsp_files_destination).resolve()

        dest_root.mkdir(parents=True, exist_ok=True)

        new_copies, new_data = rewrite_bloop(data, lsp_files_destination)

        copies.update(new_copies)

        os.remove(input_path)

        out = input_path
        out.write_text(json.dumps(new_data, indent=2, default=str) + "\n",
                       encoding="utf-8")

        print(f"Wrote rewritten JSON to {out}")
        print(f"Destination root: {dest_root}")

    if copies:
        print("Copying ", len(copies), " files...")
        for src, dst in copies.items():
            src_path = Path(src)
            dst_path = Path(dst)
            if src_path.exists():
                copy_any(src_path, dst_path)
        print(f"Copied/resolved {len(copies)} on-disk paths")
    else:
        print("No on-disk paths were resolved"
              "(they may be relative/missing).")


# This could be a lot more sophisticated, but it works well enough for
# our compile_commands.json files.
def normalize_token(token: str, tokens: List[str] = []) -> List[str]:
    """Return new argv with concatenated flags split into separate tokens.
    E.g. ['-isystemfoo'] -> ['-isystem','foo']"""

    if len(token) == 0:
        return tokens

    if token.startswith("-stdlib++"):
        tokens.append("-stdlib++")
        next_token = token[len("-stdlib++"):]
        return normalize_token(next_token, tokens)

    if token.startswith("-isystem"):
        tokens.append("-isystem")
        next_token = token[len("-isystem"):]
        return normalize_token(next_token, tokens)

    tokens.append(token)
    return tokens


KNOWN = []


def copy_any(src: Path, dst: Path):
    if str(dst) in KNOWN:
        return
    KNOWN.append(str(dst))

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.is_symlink():
            target = os.readlink(src)
            try:
                if dst.exists() or dst.is_symlink():
                    if dst.is_dir() and not dst.is_symlink():
                        shutil.rmtree(dst)
                    else:
                        dst.unlink()
            except FileNotFoundError:
                pass
            os.symlink(target, dst)
        elif src.is_dir():
            if dst.exists():
                for root, dirs, files in os.walk(src):
                    rel = Path(root).relative_to(src)
                    (dst / rel).mkdir(parents=True, exist_ok=True)
                    for fn in files:
                        s = Path(root) / fn
                        d = dst / rel / fn
                        shutil.copy2(s, d)
            else:
                shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)
    except Exception:
        pass


def rewrite_compile_commands(compile_commands: List[Any], dest_root: Path):

    copies = {}

    for compile_command in compile_commands:
        if not isinstance(compile_command, dict):
            print("ERROR: compile_commands.json on unexpected form",
                  file=sys.stderr)
            sys.exit(2)

        file = compile_command.get("file")

        command = compile_command.get("command")
        commands = []
        for item in command.split():  # type: ignore
            commands.append(item.strip("\'"))

        # First we process the command
        # Split argv into tokens, breaking up overconcatenated flags
        # such as '-isystemexternal/foo' into '-isystem' 'external/foo'
        tokens = []
        for token in commands:
            expanded = normalize_token(token, [])
            if len(expanded) > 1:
                tokens.extend(expanded)
            else:
                tokens.append(token)

        # After activating the almonds we can now find the tokens which
        # represent paths, rewrite and record them for copying
        next = []
        for arg in tokens:
            if Path(arg).exists():
                new_path = dest_root / Path(arg)
                copies[str(arg)] = str(new_path)
                next.append(str(new_path))
            else:
                next.append(arg)

        # clangd expects a single string command, so we re-concatenate
        command_str = ""
        for arg in next:
            command_str += "'" + arg + "' "
        # command_str = command_str.strip()
        compile_command["command"] = command_str

        # Next, check if file is in our source tree or not
        if file.split("/")[0] in PATHS_TO_REWRITE:  # type: ignore
            file_path = dest_root / Path(file)  # type: ignore
            copies[str(file)] = str(file_path)
            compile_command["file"] = str(file_path)

    # Now, copy all the files we found
    print("Copying ", len(copies), " files...")
    for src, dst in copies.items():
        src_path = Path(src)
        dst_path = Path(dst)
        if src_path.exists():
            copy_any(src_path, dst_path)

    print("Moved ", len(copies), " files to ", dest_root)

    return compile_commands


# Process compile_commands.json for clangd
# Copies all file paths which point to ephemeral locations
# into lsp_files/clangd/ preserving relative structure and
# rewrites compile_commands.json to point to them.
# Also tries to rewrite flags which are hard to read, like
# '-isystem<path>' => '-isystem' '<path>'
def process_clangd_artifacts(lsp_files_destination: Path):
    workspace = Path(os.getcwd())
    input_path = workspace / "compile_commands.json"

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: failed to parse JSON: {e}", file=sys.stderr)
        sys.exit(2)

    dest_root = Path(lsp_files_destination).resolve()

    dest_root.mkdir(parents=True, exist_ok=True)

    new_data = rewrite_compile_commands(data, dest_root)

    # This is OK since any non-ascenium users of deploy.py will only use it
    # for bloop
    out = Path("aptos-sim/compile_commands.json")
    out.write_text(json.dumps(new_data, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote rewritten JSON to {out}")
    print(f"Destination root: {dest_root}")
    return


def main():
    # Build the json and do the thing
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
            print("Error: 'code' process is running."
                  "Please close it before proceeding.")
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
        os.path.join(workspace, "bazel-" + os.path.basename(workspace)))

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

    # Now, rewrite it.
    os.chdir(workspace)
    if args.check_bloop:
        process_bloop_artifacts(Path("lsp_files/bloop/"))
    else:
        process_clangd_artifacts(Path("lsp_files/clangd/"))


if __name__ == "__main__":
    main()
