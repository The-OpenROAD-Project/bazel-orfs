"""Lint Yosys command implementations.

Each function is registered as a TCL command in the lint Yosys
interpreter. Commands handle the two ORFS invocation modes:
1. Canonicalization: lightweight Verilog parsing → .rtlil
2. Synthesis: estimate cell counts → mock netlist + synth_stat.txt
"""

import json
import os
import re
import sys


class MockSynthState:
    """Tracks state across lint Yosys commands."""

    def __init__(self):
        self.design_name = os.environ.get("DESIGN_NAME", "")
        self.verilog_files = []
        self.modules = (
            {}
        )  # name -> {ports: [...], regs: N, assigns: N, instances: [...]}
        self.top_module = ""
        self.cell_count_estimate = 0

    @property
    def results_dir(self):
        return os.environ.get("RESULTS_DIR", ".")

    @property
    def log_dir(self):
        return os.environ.get("LOG_DIR", ".")

    @property
    def reports_dir(self):
        return os.environ.get("REPORTS_DIR", ".")


_state = MockSynthState()


def get_state():
    return _state


def reset_state():
    global _state
    _state = MockSynthState()


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _touch(path, content=""):
    _ensure_dir(path)
    with open(path, "w") as f:
        f.write(content)


# --- Simple Verilog parser ---


def parse_verilog(content):
    """Extract module structure from Verilog/SystemVerilog source.

    Returns dict: module_name -> {ports, regs, assigns, instances, lines}
    """
    modules = {}
    current_module = None
    reg_count = 0
    assign_count = 0
    instances = []
    ports = []
    line_count = 0

    for line in content.splitlines():
        line_stripped = line.strip()
        line_count += 1

        # Module declaration
        m = re.match(r"module\s+(\w+)", line_stripped)
        if m:
            if current_module:
                modules[current_module] = {
                    "ports": ports,
                    "regs": reg_count,
                    "assigns": assign_count,
                    "instances": instances,
                    "lines": line_count,
                }
            current_module = m.group(1)
            reg_count = 0
            assign_count = 0
            instances = []
            ports = []
            line_count = 0

        # Port declarations
        m = re.match(
            r"(input|output|inout)\s+(?:wire|reg|logic)?\s*(?:\[(\d+):(\d+)\])?\s*(\w+)",
            line_stripped,
        )
        if m and current_module:
            ports.append(m.group(4))

        # Register declarations
        m = re.match(r"(?:reg|logic)\s+(?:\[(\d+):(\d+)\])?\s*(\w+)", line_stripped)
        if m and current_module:
            if m.group(1) and m.group(2):
                width = abs(int(m.group(1)) - int(m.group(2))) + 1
                reg_count += width
            else:
                reg_count += 1

        # Assign statements
        if line_stripped.startswith("assign ") and current_module:
            assign_count += 1

        # Module instantiations (heuristic: word followed by word followed by ()
        m = re.match(r"(\w+)\s+(\w+)\s*\(", line_stripped)
        if m and current_module:
            inst_type = m.group(1)
            if inst_type not in (
                "module",
                "input",
                "output",
                "inout",
                "wire",
                "reg",
                "logic",
                "assign",
                "always",
                "initial",
                "if",
                "else",
                "for",
                "while",
                "case",
                "function",
                "task",
                "generate",
                "begin",
                "end",
            ):
                instances.append(inst_type)

        # End of module
        if "endmodule" in line_stripped and current_module:
            modules[current_module] = {
                "ports": ports,
                "regs": reg_count,
                "assigns": assign_count,
                "instances": instances,
                "lines": line_count,
            }
            current_module = None

    return modules


def estimate_cells(modules, top_module=None):
    """Estimate cell count from module structure.

    Heuristics:
    - reg [N-1:0] → N flip-flops
    - assign (N-bit) → ~N cells
    - always_comb (M lines) → ~2M cells
    - Module instantiation → recursive sum
    """
    if not modules:
        return 100  # default estimate

    if top_module and top_module in modules:
        mod = modules[top_module]
    else:
        # Use largest module as top
        mod = max(modules.values(), key=lambda m: m["lines"])

    cells = 0
    # Heuristic multipliers — calibrate from real synth_stat.txt
    # via mock-train skill. Current values are rough estimates.
    CELLS_PER_ASSIGN = 4
    CELLS_PER_LINE = 2
    UNKNOWN_MODULE_CELLS = 100

    cells += mod["regs"]  # flip-flops
    cells += mod["assigns"] * CELLS_PER_ASSIGN
    cells += mod["lines"] * CELLS_PER_LINE
    for inst in mod["instances"]:
        if inst in modules:
            sub = modules[inst]
            cells += (
                sub["regs"]
                + sub["assigns"] * CELLS_PER_ASSIGN
                + sub["lines"] * CELLS_PER_LINE
            )
        else:
            cells += UNKNOWN_MODULE_CELLS
    return max(cells, 10)


# --- Yosys commands ---


def cmd_read_verilog(interp, args):
    """read_verilog ?-sv? ?-defer? <file>"""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    for path in remaining:
        if os.path.isfile(path):
            _state.verilog_files.append(path)
            with open(path) as f:
                content = f.read()
            parsed = parse_verilog(content)
            _state.modules.update(parsed)
            print(
                f"lint-yosys: read_verilog {path}" f" ({len(parsed)} modules)",
                file=sys.stderr,
            )
            if not parsed:
                print(
                    f"lint-yosys: WARNING: {path}" " contains 0 modules",
                    file=sys.stderr,
                )
        else:
            print(
                f"lint-yosys: ERROR: file not found:" f" {path}",
                file=sys.stderr,
            )
    return ""


def cmd_read_rtlil(interp, args):
    """read_rtlil / read_checkpoint <file>"""
    if args:
        path = args[-1]
        print(f"lint-yosys: read_rtlil {path}", file=sys.stderr)
    return ""


def cmd_hierarchy(interp, args):
    """hierarchy -top <module>"""
    remaining = list(args)
    while remaining:
        if remaining[0] == "-top" and len(remaining) > 1:
            _state.top_module = remaining[1]
            remaining = remaining[2:]
        elif remaining[0] == "-check":
            remaining.pop(0)
        else:
            remaining.pop(0)
    if not _state.top_module and _state.design_name:
        _state.top_module = _state.design_name
    if _state.top_module and _state.modules and _state.top_module not in _state.modules:
        print(
            f"lint-yosys: ERROR: top module"
            f" '{_state.top_module}' not found in"
            f" loaded modules"
            f" ({list(_state.modules.keys())})",
            file=sys.stderr,
        )
    return ""


def cmd_synth(interp, args):
    """synth — mock synthesis (estimate cell counts)."""
    _state.cell_count_estimate = estimate_cells(_state.modules, _state.top_module)
    print(
        f"lint-yosys: synth (est. {_state.cell_count_estimate} cells)", file=sys.stderr
    )
    return ""


def cmd_write_verilog(interp, args):
    """write_verilog ?flags? <path>"""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
        name = _state.top_module or _state.design_name or "mock_design"
        # Generate mock netlist with port list from parsed modules
        ports_str = ""
        if name in _state.modules:
            ports = _state.modules[name]["ports"]
            if ports:
                ports_str = ", ".join(ports)
        netlist = (
            f"// Mock synthesized netlist ({_state.cell_count_estimate} est. cells)\n"
        )
        netlist += f"module {name}({ports_str});\n"
        netlist += f"endmodule\n"
        _touch(path, netlist)
        print(f"lint-yosys: write_verilog {path}", file=sys.stderr)
    return ""


def cmd_write_rtlil(interp, args):
    """write_rtlil <path> — canonicalized RTLIL output."""
    if args:
        path = args[-1]
        # Write a minimal RTLIL with module declarations
        content = "# Mock RTLIL\n"
        for name, info in _state.modules.items():
            content += f"module \\{name}\n"
            for port in info.get("ports", []):
                content += f"  wire \\{port}\n"
            content += f"end\n"
        _touch(path, content)
        print(f"lint-yosys: write_rtlil {path}", file=sys.stderr)
    return ""


def cmd_stat(interp, args):
    """stat — produce synthesis statistics."""
    cells = _state.cell_count_estimate or estimate_cells(
        _state.modules, _state.top_module
    )
    _state.cell_count_estimate = cells
    name = _state.top_module or _state.design_name or "mock"
    report = f"""
=== {name} ===

   Number of wires:              {cells // 3}
   Number of wire bits:          {cells}
   Number of public wires:       {len(_state.modules.get(name, {}).get('ports', []))}
   Number of memories:           0
   Number of memory bits:        0
   Number of processes:          0
   Number of cells:              {cells}

   Chip area for module '\\{name}': {cells * 0.5:.1f}
"""
    print(report)
    return report


def cmd_tee(interp, args):
    """tee -o <file> <command...> — capture command output to file."""
    remaining = list(args)
    output_file = None
    append = False
    while remaining:
        if remaining[0] == "-o":
            remaining.pop(0)
            output_file = remaining.pop(0) if remaining else None
        elif remaining[0] == "-a":
            remaining.pop(0)
            output_file = remaining.pop(0) if remaining else None
            append = True
        else:
            break
    # Execute remaining as command
    result = ""
    if remaining:
        result = interp._invoke(remaining)
    if output_file:
        _ensure_dir(output_file)
        mode = "a" if append else "w"
        with open(output_file, mode) as f:
            f.write(result + "\n")
    return result


def cmd_write_file(interp, args):
    """write_file <path> — generic file write."""
    if args:
        _touch(args[-1], "")
    return ""


def cmd_opt_clean(interp, args):
    return ""


def cmd_opt(interp, args):
    return ""


def cmd_flatten(interp, args):
    return ""


def cmd_abc(interp, args):
    return ""


def cmd_techmap(interp, args):
    return ""


def cmd_dfflibmap(interp, args):
    return ""


def cmd_memory(interp, args):
    return ""


def cmd_memory_libmap(interp, args):
    return ""


def cmd_proc(interp, args):
    return ""


def cmd_clean(interp, args):
    return ""


def cmd_rename(interp, args):
    return ""


def cmd_check(interp, args):
    return ""


def cmd_select(interp, args):
    return ""


def cmd_delete(interp, args):
    return ""


def cmd_setattr(interp, args):
    return ""


def cmd_log(interp, args):
    """log <message> — print to stderr."""
    print(" ".join(args), file=sys.stderr)
    return ""


def cmd_read_liberty(interp, args):
    return ""


def cmd_scratchpad(interp, args):
    return ""


def cmd_design(interp, args):
    return ""


def cmd_autoname(interp, args):
    return ""


def cmd_chformal(interp, args):
    return ""


def cmd_async2sync(interp, args):
    return ""


def cmd_dff2dffe(interp, args):
    return ""


def cmd_opt_merge(interp, args):
    return ""


def cmd_opt_muxtree(interp, args):
    return ""


def cmd_opt_reduce(interp, args):
    return ""


def cmd_opt_expr(interp, args):
    return ""


def cmd_peepopt(interp, args):
    return ""


def cmd_wreduce(interp, args):
    return ""


def cmd_share(interp, args):
    return ""


def cmd_alumacc(interp, args):
    return ""


def cmd_pmuxtree(interp, args):
    return ""


def cmd_muxcover(interp, args):
    return ""


def cmd_write_json(interp, args):
    """write_json <path> — write memory configuration."""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
        _touch(path, json.dumps({}, indent=2) + "\n")
        print(f"lint-yosys: write_json {path}", file=sys.stderr)
    return ""


def register_all(interp):
    """Register all lint Yosys commands on a TclInterpreter."""
    commands = {
        # I/O
        "read_verilog": cmd_read_verilog,
        "read_rtlil": cmd_read_rtlil,
        "read_checkpoint": cmd_read_rtlil,
        "hierarchy": cmd_hierarchy,
        "write_verilog": cmd_write_verilog,
        "write_rtlil": cmd_write_rtlil,
        "write_json": cmd_write_json,
        "write_file": cmd_write_file,
        # Synthesis
        "synth": cmd_synth,
        "stat": cmd_stat,
        "tee": cmd_tee,
        # Passes (no-ops)
        "opt_clean": cmd_opt_clean,
        "opt": cmd_opt,
        "flatten": cmd_flatten,
        "abc": cmd_abc,
        "techmap": cmd_techmap,
        "dfflibmap": cmd_dfflibmap,
        "memory": cmd_memory,
        "memory_libmap": cmd_memory_libmap,
        "proc": cmd_proc,
        "clean": cmd_clean,
        "rename": cmd_rename,
        "check": cmd_check,
        "select": cmd_select,
        "delete": cmd_delete,
        "setattr": cmd_setattr,
        "log": cmd_log,
        "read_liberty": cmd_read_liberty,
        "scratchpad": cmd_scratchpad,
        "design": cmd_design,
        "autoname": cmd_autoname,
        "chformal": cmd_chformal,
        "async2sync": cmd_async2sync,
        "dff2dffe": cmd_dff2dffe,
        "opt_merge": cmd_opt_merge,
        "opt_muxtree": cmd_opt_muxtree,
        "opt_reduce": cmd_opt_reduce,
        "opt_expr": cmd_opt_expr,
        "peepopt": cmd_peepopt,
        "wreduce": cmd_wreduce,
        "share": cmd_share,
        "alumacc": cmd_alumacc,
        "pmuxtree": cmd_pmuxtree,
        "muxcover": cmd_muxcover,
    }
    for name, func in commands.items():
        interp.register_command(name, func)
