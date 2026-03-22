#!/usr/bin/env python3
"""Mock openroad binary for testing the ORFS Bazel rules.

Creates dummy output files by scanning TCL scripts for write commands,
allowing the ORFS flow to proceed without a real OpenROAD installation.
"""

import os
import pathlib
import re
import sys

# Patterns that write output files in ORFS TCL scripts
WRITE_PATTERNS = {
    "odb": re.compile(r"(?:orfs_write_db|write_db)\s+(.+\.odb)"),
    "sdc": re.compile(r"write_sdc\s+(.+\.sdc)"),
    "v": re.compile(r"write_verilog\s+(.+\.v)"),
    "spef": re.compile(r"write_spef\s+(.+\.spef)"),
}

ABSTRACT_PATTERNS = re.compile(r"write_abstract_lef|write_timing_model")


def extract_output_files(tcl_content):
    """Extract output filenames from TCL script content.

    Returns a list of basenames (e.g. '2_floorplan.odb') that the script
    would write to $RESULTS_DIR.
    """
    files = []
    for line in tcl_content.splitlines():
        for ext, pattern in WRITE_PATTERNS.items():
            match = pattern.search(line)
            if match:
                path = match.group(1).strip()
                basename = os.path.basename(path)
                if basename:
                    files.append(basename)
    return files


def needs_abstract(tcl_content):
    """Check if the TCL script generates abstract views (.lef and .lib)."""
    return bool(ABSTRACT_PATTERNS.search(tcl_content))


def create_outputs(tcl_path, results_dir, design_name=None):
    """Scan a TCL file and create dummy output files in results_dir.

    Returns list of created file paths.
    """
    created = []

    try:
        with open(tcl_path) as f:
            content = f.read()
    except (OSError, IOError):
        return created

    if not results_dir:
        return created

    os.makedirs(results_dir, exist_ok=True)

    for basename in extract_output_files(content):
        path = os.path.join(results_dir, basename)
        pathlib.Path(path).touch()
        created.append(path)

    if needs_abstract(content) and design_name:
        for suffix in [".lef", "_typ.lib"]:
            path = os.path.join(results_dir, design_name + suffix)
            pathlib.Path(path).touch()
            created.append(path)

    return created


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    for arg in argv:
        if arg == "-version":
            print("OpenROAD v0.0.0 (mock)")
            return 0
        if arg == "-help":
            print("mock openroad (CI stub)")
            return 0

    results_dir = os.environ.get("RESULTS_DIR", "")
    design_name = os.environ.get("DESIGN_NAME", "")

    for arg in argv:
        if os.path.isfile(arg):
            create_outputs(arg, results_dir, design_name)

    print("mock openroad (CI stub)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
