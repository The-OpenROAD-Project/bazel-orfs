#!/usr/bin/env python3
"""Lint OpenROAD binary — estimation engine for ORFS flows.

Replaces real OpenROAD with a seconds-fast linter that:
- Executes ORFS TCL scripts via a minimal TCL interpreter
- Creates all expected output files (ODB, SDC, LEF, LIB, logs, reports)
- Estimates design complexity, stage runtimes, and suggests parameters
"""

import os
import sys


def find_module_file(name):
    """Find a Python module file relative to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Direct sibling
    path = os.path.join(script_dir, name)
    if os.path.isfile(path):
        return path
    # Runfiles paths
    for runfiles_base in [
        os.path.join(script_dir, "openroad.runfiles", "lint-openroad+", "src", "bin"),
        os.path.join(script_dir, "openroad.runfiles", "lint-openroad", "src", "bin"),
    ]:
        path = os.path.join(runfiles_base, name)
        if os.path.isfile(path):
            return path
    return None


def setup_module_path():
    """Add the directory containing our modules to sys.path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    # Find tcl_interpreter from lint-tcl module.
    # Walk up from script_dir to find the runfiles root.
    d = script_dir
    for _ in range(6):
        for name in ["lint-tcl+", "lint-tcl"]:
            candidate = os.path.join(d, name, "src", "bin")
            if os.path.isfile(os.path.join(
                candidate, "tcl_interpreter.py"
            )):
                if candidate not in sys.path:
                    sys.path.insert(0, candidate)
                return
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    # Local dev: sibling mock/tcl directory
    tcl_dir = os.path.normpath(os.path.join(
        script_dir, "..", "..", "..", "tcl", "src", "bin"
    ))
    if os.path.isfile(os.path.join(
        tcl_dir, "tcl_interpreter.py"
    )):
        if tcl_dir not in sys.path:
            sys.path.insert(0, tcl_dir)


def _create_fallback_outputs(state):
    """Create expected output files when TCL execution fails.

    Scans RESULTS_DIR for what's expected based on env vars.
    """
    results = state.results_dir
    if not results or results == ".":
        return
    os.makedirs(results, exist_ok=True)
    # The make wrapper copies the last substep ODB.
    # Create any ODB that doesn't exist yet.
    design = state.design_name or "mock"
    for pattern in [
        "1_synth.odb",
        "2_1_floorplan.odb", "2_2_floorplan_macro.odb",
        "2_3_floorplan_tapcell.odb", "2_4_floorplan_pdn.odb",
        "3_1_place_gp_skip_io.odb", "3_2_place_iop.odb",
        "3_3_place_gp.odb", "3_4_place_resized.odb",
        "3_5_place_dp.odb",
        "4_1_cts.odb",
        "5_1_grt.odb",
        "5_2_route.odb", "5_3_fillcell.odb",
        "6_1_merge.odb",
    ]:
        path = os.path.join(results, pattern)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("lint-odb-v1\n")
    # SDC files
    for sdc in [
        "2_1_floorplan.sdc", "2_floorplan.sdc",
        "3_place.sdc", "4_cts.sdc",
        "5_1_grt.sdc", "5_route.sdc",
        "6_final.sdc",
    ]:
        path = os.path.join(results, sdc)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("# Mock SDC\n")
    # Abstract outputs
    lef = os.path.join(results, f"{design}.lef")
    lib = os.path.join(results, f"{design}_typ.lib")
    if not os.path.exists(lef):
        with open(lef, "w") as f:
            f.write(
                f"VERSION 5.8 ;\nMACRO {design}\n"
                f"  CLASS BLOCK ;\n  SIZE 10.0 BY 10.0 ;\n"
                f"END {design}\nEND LIBRARY\n"
            )
    if not os.path.exists(lib):
        with open(lib, "w") as f:
            f.write(
                f"library ({design}_typ) {{\n"
                f"  cell ({design}) {{ area : 1.0 ; }}\n}}\n"
            )


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Handle simple flags
    for arg in argv:
        if arg in ("-version", "--version"):
            print("OpenROAD v0.0.0-mock (estimation engine)")
            return 0
        if arg in ("-help", "--help"):
            print("lint-openroad: estimation engine for ORFS flows")
            print("Usage: openroad [-version] [-exit] [script.tcl ...]")
            return 0

    setup_module_path()
    from tcl_interpreter import TclInterpreter
    import openroad_commands

    interp = TclInterpreter()
    openroad_commands.register_all(interp)
    openroad_commands.reset_state()

    # Load design name from environment
    state = openroad_commands.get_state()
    state.design_name = os.environ.get("DESIGN_NAME", "")
    state.platform = os.environ.get("PLATFORM", "")

    # Ensure output directories exist
    for d in [state.results_dir, state.log_dir, state.reports_dir, state.objects_dir]:
        if d and d != ".":
            os.makedirs(d, exist_ok=True)

    # Parse arguments
    scripts = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-exit", "-no_init", "-no_splash", "-gui"):
            pass
        elif arg in ("-threads", "-log", "-metrics"):
            i += 1  # skip value
        elif arg.startswith("-"):
            pass  # ignore unknown flags
        elif os.path.isfile(arg) or arg.endswith(".tcl"):
            scripts.append(arg)
        i += 1

    # Execute scripts
    for script_path in scripts:
        if not os.path.isfile(script_path):
            print(f"lint-openroad: warning: script not found: {script_path}",
                  file=sys.stderr)
            continue
        try:
            interp.eval_file(script_path)
        except Exception as e:
            print(f"lint-openroad: error in {script_path}: {e}",
                  file=sys.stderr)
            # Don't fail — ORFS scripts may reference things we don't
            # implement yet. Create expected output files based on env vars.
            _create_fallback_outputs(state)

    print("lint-openroad: done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
