#!/usr/bin/env python3
"""Mock Yosys binary — estimation engine for ORFS synthesis.

Replaces real Yosys with a seconds-fast linter that:
- Parses Verilog source for module structure (canonicalization)
- Estimates cell counts and area (synthesis)
- Creates all expected output files (netlist, synth_stat.txt, mem.json)
"""

import os
import sys


def setup_module_path():
    """Add the directory containing our modules to sys.path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    # Runfiles: tcl_interpreter.py comes from mock-openroad module.
    d = script_dir
    for _ in range(6):
        for name in ["mock-openroad+", "mock-openroad"]:
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


def parse_yosys_args(argv):
    """Parse yosys command-line arguments.

    Returns (commands_list, script_files, verilog_files, flags).
    - commands_list: list of -c/-p command strings to execute
    - script_files: list of -s script files to execute
    - verilog_files: positional Verilog files
    - flags: dict of parsed flags
    """
    commands = []
    scripts = []
    verilog_files = []
    flags = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-V", "-version", "--version"):
            flags["version"] = True
        elif arg in ("-h", "-help", "--help"):
            flags["help"] = True
        elif arg == "-c":
            i += 1
            if i < len(argv):
                commands.append(argv[i])
        elif arg == "-p":
            i += 1
            if i < len(argv):
                commands.append(argv[i])
        elif arg == "-s":
            i += 1
            if i < len(argv):
                scripts.append(argv[i])
        elif arg == "-l":
            i += 1  # skip log file
        elif arg == "-o":
            i += 1  # skip output file
            flags["output"] = argv[i] if i < len(argv) else None
        elif arg == "-D":
            i += 1  # skip define
        elif arg == "-f":
            i += 1  # skip frontend
        elif arg == "-b":
            i += 1  # skip backend
        elif arg.startswith("-"):
            pass  # ignore other flags
        else:
            verilog_files.append(arg)
        i += 1
    return commands, scripts, verilog_files, flags


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    commands, scripts, verilog_files, flags = parse_yosys_args(argv)

    if flags.get("version"):
        print("Yosys 0.0.0-mock (estimation engine)")
        return 0

    if flags.get("help"):
        print("mock-yosys: estimation engine for ORFS synthesis")
        return 0

    setup_module_path()

    from tcl_interpreter import TclInterpreter
    import yosys_commands

    interp = TclInterpreter()
    yosys_commands.register_all(interp)

    # Ensure output directories exist
    for env_var in ["RESULTS_DIR", "LOG_DIR", "REPORTS_DIR", "OBJECTS_DIR"]:
        d = os.environ.get(env_var, "")
        if d and d != ".":
            os.makedirs(d, exist_ok=True)

    # Execute -c commands (TCL)
    for cmd in commands:
        try:
            interp.eval(cmd)
        except Exception as e:
            print(f"mock-yosys: error in command: {e}", file=sys.stderr)

    # Execute -s script files
    for script in scripts:
        if os.path.isfile(script):
            try:
                interp.eval_file(script)
            except Exception as e:
                print(f"mock-yosys: error in {script}: {e}", file=sys.stderr)

    # Create fallback outputs if TCL execution didn't
    results_dir = os.environ.get("RESULTS_DIR", "")
    design = os.environ.get("DESIGN_NAME", "mock")
    if results_dir:
        state = yosys_commands.get_state()
        for name_f, content in [
            ("1_2_yosys.v",
             f"module {design}(); endmodule\n"),
            ("1_1_yosys_canonicalize.rtlil",
             f"# Mock RTLIL\nmodule \\{design}\nend\n"),
            ("mem.json", "{}\n"),
        ]:
            path = os.path.join(results_dir, name_f)
            if not os.path.exists(path):
                os.makedirs(results_dir, exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
