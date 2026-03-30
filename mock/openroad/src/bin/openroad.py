#!/usr/bin/env python3
"""Mock openroad binary for testing the ORFS Bazel rules.

Creates dummy output files by scanning TCL scripts for write commands,
allowing the ORFS flow to proceed without a real OpenROAD installation.
"""

import glob
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


def extract_ports_from_rtlil(results_dir, design_name):
    """Extract port names and directions from the RTLIL for design_name.

    Scans *.rtlil files in results_dir for the module matching design_name
    and returns a list of (name, direction, width) tuples.
    """
    ports = []
    rtlil_files = glob.glob(os.path.join(results_dir, "*.rtlil"))
    for rtlil_path in rtlil_files:
        try:
            with open(rtlil_path) as f:
                in_module = False
                for line in f:
                    stripped = line.strip()
                    if stripped == f"module \\{design_name}":
                        in_module = True
                        continue
                    if in_module and stripped.startswith("end"):
                        break
                    if not in_module:
                        continue
                    m = re.match(
                        r"wire\s+(?:width\s+(\d+)\s+)?(input|output|inout)\s+\d+\s+\\(\S+)",
                        stripped,
                    )
                    if m:
                        width = int(m.group(1)) if m.group(1) else 1
                        direction = m.group(2)
                        name = m.group(3)
                        ports.append((name, direction, width))
        except (OSError, IOError):
            continue
        if ports:
            break
    return ports


def generate_liberty(design_name, ports):
    """Generate a minimal liberty string with pin declarations.

    Multi-bit ports use bus() with a type definition so yosys can
    reconstruct the port width from the liberty model.
    """
    lines = [f'library ("{design_name}_typ") {{']

    # Emit bus_type definitions for each unique width
    widths = sorted({w for _, _, w in ports if w > 1})
    for w in widths:
        lines.append(f"  type (bus{w}) {{")
        lines.append(f"    base_type: array;")
        lines.append(f"    data_type: bit;")
        lines.append(f"    bit_width: {w};")
        lines.append(f"    bit_from: {w - 1};")
        lines.append(f"    bit_to: 0;")
        lines.append(f"  }}")

    lines.append(f"  cell ({design_name}) {{")
    for name, direction, width in ports:
        if width > 1:
            lines.append(f"    bus ({name}) {{")
            lines.append(f"      bus_type: bus{width};")
            lines.append(f"      direction: {direction};")
            lines.append(f"    }}")
        else:
            lines.append(f"    pin ({name}) {{")
            lines.append(f"      direction: {direction};")
            lines.append("    }")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


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
        lef_path = os.path.join(results_dir, design_name + ".lef")
        pathlib.Path(lef_path).touch()
        created.append(lef_path)

        ports = extract_ports_from_rtlil(results_dir, design_name)
        lib_path = os.path.join(results_dir, design_name + "_typ.lib")
        with open(lib_path, "w") as f:
            f.write(generate_liberty(design_name, ports))
        created.append(lib_path)

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
