#! /usr/bin/env python3

import argparse
import os
import subprocess
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

DEFAULT_SEARCH_PATHS = [
    "/lib64",
    "/usr/lib/x86_64-linux-gnu",
]

ELF_MAGIC = b"\x7fELF"


def magic(path: str) -> Optional[bytes]:
    """
    Returns first few bytes from the given file.

    Parameters
    ----------
    path : str
        Path to the file

    Returns
    -------
    Optional[bytes]
        bytes or None
    """
    if not os.path.isfile(path):
        return None

    try:
        with open(path, "rb") as f:
            return f.read(len(ELF_MAGIC))
    except FileNotFoundError:
        return None

    return None


def patch_prepare(args: argparse.Namespace, root: str, file: str) -> List:
    """
    Reads patchelf information (like rpath or interpreter)
    and prepares patchelf commands. It also fixes links.

    Parameters
    ----------
    args : argparse.Namespace
        Program arguments
    root : str
        Root directory of the processed file
    file : str
        Name of the processed file

    Returns
    -------
    List
        List of prepared commands

    Raises
    ------
    subprocess.CalledProcessError
        Exception raised when subprocess fails
    """
    link = os.path.join(root, file)
    if os.path.islink(link) and os.path.isabs(os.readlink(link)):
        readlink = os.path.relpath(os.readlink(link), start=os.path.abspath("/"))
        target = os.path.join(args.directory, readlink)
        link_to_target = os.path.relpath(target, start=root)
        os.unlink(link)
        os.symlink(link_to_target, link)
        return []

    if magic(os.path.join(root, file)) != ELF_MAGIC:
        return []

    needed_result = subprocess.run(
        [args.patchelf, "--print-needed", file], cwd=root, capture_output=True
    )
    needed_libs = needed_result.stdout.decode("utf-8").strip()
    if not needed_libs:
        return []

    rpath_fragments = (
        subprocess.check_output([args.patchelf, "--print-rpath", file], cwd=root)
        .decode("utf-8")
        .strip()
    )
    rpaths = []
    for rpath in rpath_fragments.split(":") + DEFAULT_SEARCH_PATHS:
        if not rpath:
            continue

        if "$ORIGIN" in rpath:
            rpaths.append(rpath)
        else:
            elf = os.path.join("/", os.path.relpath(root, start=args.directory))
            elf_to_rpath = os.path.relpath(rpath, start=elf)
            rpaths.append(os.path.join("$ORIGIN", elf_to_rpath))

    rpath = ":".join(rpaths).encode("utf-8")
    cmds = [
        (
            [
                args.patchelf,
                "--force-rpath",
                "--set-rpath",
                rpath,
                "--no-default-lib",
                file,
            ],
            root,
        )
    ]

    interpreter_result = subprocess.run(
        [args.patchelf, "--print-interpreter", file], cwd=root, capture_output=True
    )
    if interpreter_result.returncode != 0:
        return cmds

    interpreter_old = interpreter_result.stdout.decode("utf-8").strip()
    execution_root = os.path.normpath(os.path.join(args.directory, "..", ".."))
    interp = os.path.relpath(interpreter_old, start="/")
    execution_root_to_interp = os.path.relpath(
        os.path.join(args.directory, interp), execution_root
    )
    cmds.append(
        ([args.patchelf, "--set-interpreter", execution_root_to_interp, file], root),
    )
    return cmds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="Directory to patch.")
    parser.add_argument(
        "-p", "--patchelf", default="patchelf", help="`patchelf` binary to use."
    )
    parser.add_argument(
        "-j", "--jobs", default=None, type=int, help="Number of threads to use."
    )
    args = parser.parse_args()

    if args.jobs is None:
        args.jobs = multiprocessing.cpu_count() // 2

    futures, commands, failed_files = [], [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        for root, dirs, files in os.walk(args.directory):
            for file in files:
                futures.append(
                    (
                        executor.submit(
                            patch_prepare,
                            args,
                            root,
                            file,
                        ),
                        (root, file),
                    )
                )
        for future, (root, file) in futures:
            try:
                command = future.result()
            except subprocess.CalledProcessError as ex:
                failed_files.append((root, file, ex))
                continue
            commands.extend(command)

    if failed_files:
        error_msg = "\n".join([f"{os.path.join(r, f)}" for r, f, _ in failed_files])
        raise Exception(
            f"Cannot prepare patchelf command for:\n{error_msg}"
        ) from failed_files[0][2]

    for command, root in commands:
        subprocess.check_call(command, cwd=root)


if __name__ == "__main__":
    main()
