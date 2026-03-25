#! /usr/bin/env python3

import argparse
import os
import re
import shutil
import stat
import subprocess
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

DEFAULT_SEARCH_PATHS = [
    "/lib64",
    "/usr/lib/x86_64-linux-gnu",
]

ELF_MAGIC = b"\x7fELF"

WRAPPER_TEMPLATE = """\
#!/usr/bin/env bash
self="$(readlink -f "${{BASH_SOURCE[0]}}")"
top_dir="$(cd "$(dirname "$self")/{self_to_top}" && pwd)"
{env_exports}exec "$top_dir/{interpreter}" \\
  --inhibit-cache --inhibit-rpath "" \\
  --library-path "{library_path}" \\
  --argv0 "$self" \\
  "$top_dir/{libexec}" "$@"
"""

# Regex patterns for parsing readelf output
_NEEDED_RE = re.compile(r"\(NEEDED\)\s+Shared library: \[(.+)\]")
_RPATH_RE = re.compile(r"\((?:RPATH|RUNPATH)\)\s+Library r(?:un)?path: \[(.+)\]")
_INTERP_RE = re.compile(r"Requesting program interpreter: (.+)\]")


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


def _readelf_dynamic(root: str, file: str) -> str:
    """Run readelf -d and return stdout, or empty string on failure."""
    result = subprocess.run(["readelf", "-d", file], cwd=root, capture_output=True)
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8")


def _readelf_needed(dynamic_output: str) -> List[str]:
    """Extract NEEDED entries from readelf -d output."""
    return _NEEDED_RE.findall(dynamic_output)


def _readelf_rpath(dynamic_output: str) -> str:
    """Extract RPATH/RUNPATH from readelf -d output."""
    match = _RPATH_RE.search(dynamic_output)
    return match.group(1) if match else ""


def _readelf_interpreter(root: str, file: str) -> Optional[str]:
    """Extract PT_INTERP from readelf -l output."""
    result = subprocess.run(["readelf", "-l", file], cwd=root, capture_output=True)
    if result.returncode != 0:
        return None
    match = _INTERP_RE.search(result.stdout.decode("utf-8"))
    return match.group(1) if match else None


def patch_prepare(args: argparse.Namespace, root: str, file: str) -> Optional[dict]:
    """
    Reads ELF information and prepares wrapper info for executables.
    Also fixes absolute symlinks to be relative.

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
    Optional[dict]
        Wrapper info dict for executables with an interpreter, or None.

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
        return None

    if magic(os.path.join(root, file)) != ELF_MAGIC:
        return None

    dynamic_output = _readelf_dynamic(root, file)
    needed_libs = _readelf_needed(dynamic_output)
    if not needed_libs:
        return None

    rpath_fragments = _readelf_rpath(dynamic_output)
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

    interpreter_old = _readelf_interpreter(root, file)
    if interpreter_old is None:
        return None

    # Only wrap actual executables, not shared libraries.
    # Shared libraries may have PT_INTERP (PIE) but should not be wrapped.
    if ".so" in file:
        return None

    interpreter_rel = os.path.relpath(interpreter_old, start="/")

    # Compute absolute rpath directories relative to the extraction root
    # for use in the wrapper script's --library-path
    elf_dir = os.path.join("/", os.path.relpath(root, start=args.directory))
    abs_rpaths = []
    for rp in rpaths:
        if "$ORIGIN" in rp:
            resolved = rp.replace("$ORIGIN", elf_dir)
            rel_to_root = os.path.relpath(resolved, start="/")
            abs_rpaths.append(rel_to_root)
        else:
            abs_rpaths.append(os.path.relpath(rp, start="/"))

    wrapper_info = {
        "root": root,
        "file": file,
        "interpreter": interpreter_rel,
        "library_paths": abs_rpaths,
    }

    return wrapper_info


def find_tcl_library(directory: str) -> Optional[str]:
    """Find the TCL library directory relative to the extraction root."""
    for root, dirs, files in os.walk(directory):
        if "init.tcl" in files and "tcl" in root:
            return os.path.relpath(root, directory)
    return None


def generate_wrapper(
    args: argparse.Namespace,
    wrapper_info: dict,
    tcl_library: Optional[str] = None,
):
    """
    Moves an ELF executable to libexec/ and creates a wrapper script
    that invokes the bundled ld-linux with --inhibit-cache.

    Parameters
    ----------
    args : argparse.Namespace
        Program arguments
    wrapper_info : dict
        Dictionary with keys: root, file, interpreter, library_paths
    tcl_library : Optional[str]
        TCL library path relative to extraction root
    """
    root = wrapper_info["root"]
    file = wrapper_info["file"]
    src = os.path.join(root, file)

    # Compute the libexec destination mirroring the relative path
    rel_from_root = os.path.relpath(src, start=args.directory)
    libexec_rel = os.path.join("libexec", rel_from_root)
    libexec_abs = os.path.join(args.directory, libexec_rel)

    os.makedirs(os.path.dirname(libexec_abs), exist_ok=True)
    os.rename(src, libexec_abs)

    # Relative path from the wrapper script's directory
    # to the extraction root
    wrapper_dir = os.path.dirname(src)
    self_to_top = os.path.relpath(args.directory, start=wrapper_dir)

    library_path = ":".join("$top_dir/" + p for p in wrapper_info["library_paths"])

    env_lines = []
    if tcl_library:
        env_lines.append(
            'export TCL_LIBRARY="${TCL_LIBRARY:-' "$top_dir/" + tcl_library + '}"'
        )
    env_exports = "".join(line + "\n" for line in env_lines)

    wrapper_content = WRAPPER_TEMPLATE.format(
        self_to_top=self_to_top,
        interpreter=wrapper_info["interpreter"],
        library_path=library_path,
        libexec=libexec_rel,
        env_exports=env_exports,
    )

    with open(src, "w") as f:
        f.write(wrapper_content)
    os.chmod(
        src,
        stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
    )


def setup_interpreter(args: argparse.Namespace, interpreter_rel: str):
    """
    Copy the ld-linux interpreter to lib/ at the extraction root.

    Tools like yosys use /proc/self/exe to locate share/ relative
    to the interpreter. By placing ld-linux at {top}/lib/ (a real
    directory, not a symlink), /proc/self/exe resolves to
    {top}/lib/ld-linux and {exe_dir}/../share/yosys/ becomes
    {top}/share/yosys/ --- matching the oss-cad-suite layout.

    Returns the new interpreter path relative to the extraction root.
    """
    interp_basename = os.path.basename(interpreter_rel)
    new_rel = os.path.join("_lib", interp_basename)
    new_abs = os.path.join(args.directory, new_rel)

    if not os.path.exists(new_abs):
        real_interp = os.path.realpath(os.path.join(args.directory, interpreter_rel))
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        shutil.copy2(real_interp, new_abs)

    return new_rel


def create_share_symlinks(args: argparse.Namespace):
    """
    Create top-level share/ symlinks so that tools using
    /proc/self/exe can find their data directories.

    With the wrapper approach, /proc/self/exe resolves to
    the ld-linux interpreter. Tools like yosys check
    {exe_dir}/../share/yosys/ which becomes {top}/share/yosys/.
    """
    top_share = os.path.join(args.directory, "share")
    os.makedirs(top_share, exist_ok=True)

    for root, dirs, files in os.walk(args.directory):
        # Skip the top-level share dir itself and libexec
        rel = os.path.relpath(root, args.directory)
        if rel == "share" or rel.startswith("share/"):
            continue
        if rel.startswith("libexec"):
            continue

        # Look for share/<tool> directories
        if os.path.basename(root) == "share":
            for d in dirs:
                link = os.path.join(top_share, d)
                target = os.path.join(root, d)
                if not os.path.exists(link):
                    os.symlink(
                        os.path.relpath(target, top_share),
                        link,
                    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="Directory to patch.")
    parser.add_argument(
        "-j", "--jobs", default=None, type=int, help="Number of threads to use."
    )
    args = parser.parse_args()

    if args.jobs is None:
        args.jobs = multiprocessing.cpu_count() // 2

    futures, wrappers, failed_files = [], [], []
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
                wrapper_info = future.result()
            except subprocess.CalledProcessError as ex:
                failed_files.append((root, file, ex))
                continue
            if wrapper_info is not None:
                wrappers.append(wrapper_info)

    if failed_files:
        error_msg = "\n".join([f"{os.path.join(r, f)}" for r, f, _ in failed_files])
        raise Exception(f"Cannot read ELF info for:\n{error_msg}") from failed_files[0][
            2
        ]

    # Copy ld-linux to lib/ so /proc/self/exe resolves to a
    # known, symlink-free path. This lets tools like yosys find
    # {exe_dir}/../share/yosys/ = {top}/share/yosys/.
    interp_map = {}
    for wrapper_info in wrappers:
        old_interp = wrapper_info["interpreter"]
        if old_interp not in interp_map:
            interp_map[old_interp] = setup_interpreter(args, old_interp)
        wrapper_info["interpreter"] = interp_map[old_interp]

    tcl_library = find_tcl_library(args.directory)

    for wrapper_info in wrappers:
        generate_wrapper(args, wrapper_info, tcl_library)

    # Tools like yosys use proc_self_dirname() to find sibling
    # executables (e.g. yosys-abc). Since /proc/self/exe now
    # resolves to _lib/ld-linux, create symlinks in _lib/ for
    # all wrapped executables so they can be found as siblings.
    if wrappers:
        # After setup_interpreter, wrapper["interpreter"] is already the
        # new _lib/ path.  Use it directly.
        interp_dir = os.path.dirname(
            os.path.join(args.directory, wrappers[0]["interpreter"])
        )
        for wrapper_info in wrappers:
            name = os.path.basename(wrapper_info["file"])
            link = os.path.join(interp_dir, name)
            wrapper_path = os.path.join(wrapper_info["root"], wrapper_info["file"])
            if not os.path.exists(link):
                os.symlink(
                    os.path.relpath(wrapper_path, interp_dir),
                    link,
                )

    # Create top-level share/ symlinks so tools like yosys that
    # use /proc/self/exe to find {exe_dir}/../share/yosys/ can
    # locate their data files relative to the ld-linux location.
    create_share_symlinks(args)


if __name__ == "__main__":
    main()
