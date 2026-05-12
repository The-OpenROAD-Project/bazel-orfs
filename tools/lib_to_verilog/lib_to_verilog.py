"""Generate Verilator-compatible behavioral Verilog from Liberty (.lib) files.

Reads .lib files to extract cell definitions and generates simple behavioral
Verilog that Verilator can simulate:
  - Sequential cells (ff, latch) — clocked always blocks.
  - Combinational cells — `assign` of the Liberty `function:` expression.
Also reads LEF files to identify physical-only cells (TAPCELL, FILLER,
DECAP, etc.) that need empty module stubs.

The existing ASAP7 PDK Verilog uses UDP primitives (altos_dff_sr_err, etc.)
which Verilator doesn't support. This tool generates replacements using
standard always blocks and continuous assigns.

Usage:
    python lib_to_verilog.py --lib SEQ.lib [--lef cells.lef] --dff dff.v --empty empty.v
"""

import argparse
import gzip
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Pin:
    name: str
    direction: str  # "input" or "output"
    function: str = ""


@dataclass
class FfInfo:
    """Liberty ff() group data."""
    var1: str  # e.g. "IQN" or "IQ"
    var2: str  # e.g. "IQNN" or "IQN"
    clocked_on: str = ""
    next_state: str = ""
    clear: str = ""       # async reset (sets to 0)
    preset: str = ""      # async set (sets to 1)


@dataclass
class LatchInfo:
    """Liberty latch() group data."""
    var1: str  # e.g. "IQ"
    var2: str  # e.g. "IQN"
    enable: str = ""
    data_in: str = ""
    clear: str = ""
    preset: str = ""


@dataclass
class Cell:
    name: str
    pins: list = field(default_factory=list)
    ff: FfInfo | None = None
    latch: LatchInfo | None = None


def parse_lib_cells(text: str) -> list[Cell]:
    """Parse Liberty text and return cells that have ff or latch groups.

    Handles both multi-line and compact single-line Liberty syntax, e.g.:
        pin (CLK) { direction : input; }
        ff (IQ,IQN) { clocked_on : "CLK"; next_state : "D"; }
    """
    cells = []
    cell = None
    current_pin = None
    in_ff = False
    in_latch = False
    brace_depth = 0
    cell_depth = 0
    pin_depth = 0
    ff_depth = 0
    latch_depth = 0

    for line in text.splitlines():
        stripped = line.strip()

        # Track brace depth at start of line (before opens on this line)
        opens = stripped.count("{")
        closes = stripped.count("}")

        # Cell start — match before updating depth so cell_depth is correct
        m = re.match(r'cell\s*\(\s*(\S+)\s*\)', stripped)
        if m and not stripped.startswith("cell_"):
            brace_depth += opens - closes
            cell = Cell(name=m.group(1))
            cell_depth = brace_depth
            current_pin = None
            in_ff = False
            in_latch = False
            continue

        # Update depth for non-cell lines
        brace_depth += opens - closes

        if cell is None:
            continue

        # Cell end
        if brace_depth < cell_depth:
            has_combinational = any(
                p.direction == "output" and p.function
                for p in cell.pins
            )
            if cell.ff or cell.latch or has_combinational:
                cells.append(cell)
            cell = None
            continue

        # Pin start (don't continue — attributes may be on same line)
        m = re.search(r'(?<![pg_])pin\s*\(\s*(\S+)\s*\)', stripped)
        if m and not re.search(r'pg_pin', stripped):
            current_pin = Pin(name=m.group(1), direction="")
            pin_depth = brace_depth
            cell.pins.append(current_pin)

        # Pin end (if brace closed on same or later line)
        if current_pin and opens <= closes and brace_depth < pin_depth:
            # Process attributes on this line first, then close
            pass  # handled below after attribute extraction

        # Pin attributes (use re.search for inline)
        if current_pin:
            m = re.search(r'direction\s*:\s*(\w+)', stripped)
            if m:
                current_pin.direction = m.group(1)
            m = re.search(r'(?<!\w)function\s*:\s*"([^"]*)"', stripped)
            if m:
                current_pin.function = m.group(1)

        # Close pin after processing attributes
        if current_pin and brace_depth < pin_depth:
            current_pin = None

        # ff group start
        m = re.search(r'ff\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)', stripped)
        if m:
            cell.ff = FfInfo(var1=m.group(1), var2=m.group(2))
            in_ff = True
            ff_depth = brace_depth

        # latch group start
        m = re.search(r'latch\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)', stripped)
        if m:
            cell.latch = LatchInfo(var1=m.group(1), var2=m.group(2))
            in_latch = True
            latch_depth = brace_depth

        # ff attributes (use re.search for inline)
        if in_ff and cell.ff:
            m = re.search(r'clocked_on\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.ff.clocked_on = m.group(1)
            m = re.search(r'next_state\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.ff.next_state = m.group(1)
            m = re.search(r'clear\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.ff.clear = m.group(1)
            m = re.search(r'preset\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.ff.preset = m.group(1)

        # latch attributes
        if in_latch and cell.latch:
            m = re.search(r'enable\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.latch.enable = m.group(1)
            m = re.search(r'data_in\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.latch.data_in = m.group(1)
            m = re.search(r'clear\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.latch.clear = m.group(1)
            m = re.search(r'preset\s*:\s*"([^"]*)"', stripped)
            if m:
                cell.latch.preset = m.group(1)

        # ff/latch end
        if in_ff and brace_depth < ff_depth:
            in_ff = False
        if in_latch and brace_depth < latch_depth:
            in_latch = False

    return cells


def liberty_expr_to_verilog(expr: str) -> str:
    """Convert a Liberty Boolean expression to Verilog.

    Liberty uses: * (AND), + (OR), ! (NOT prefix), ' (NOT suffix), ^ (XOR)
    Verilog uses: & (AND), | (OR), ~ (NOT), ^ (XOR)
    """
    result = expr
    # Postfix NOT: A' -> ~A,  (A+B)' -> ~(A+B). Apply repeatedly until stable
    # so chains like A'' collapse correctly.
    pattern = re.compile(r"(\w+|\([^()]*\))'")
    while True:
        new = pattern.sub(r"~\1", result)
        if new == result:
            break
        result = new
    result = result.replace("!", "~")
    result = result.replace("*", " & ")
    result = result.replace("+", " | ")
    # XOR (^) and parentheses pass through unchanged.
    result = re.sub(r"\s+", " ", result).strip()
    return result


def generate_ff_verilog(cell: Cell) -> str:
    """Generate Verilator-compatible Verilog for a flip-flop cell."""
    ff = cell.ff
    assert ff is not None

    outputs = [p for p in cell.pins if p.direction == "output"]
    inputs = [p for p in cell.pins if p.direction == "input"]

    port_names = [p.name for p in outputs] + [p.name for p in inputs]
    port_list = ", ".join(port_names)

    lines = []
    lines.append(f"module {cell.name} ({port_list});")

    for p in outputs:
        lines.append(f"    output reg {p.name};")
    for p in inputs:
        lines.append(f"    input {p.name};")
    lines.append("")

    clk_expr = liberty_expr_to_verilog(ff.clocked_on)
    next_expr = liberty_expr_to_verilog(ff.next_state)

    # Map internal variable to output pin
    # ff.var1 is the internal state variable; find which output uses it
    out_assigns = []
    for p in outputs:
        func = p.function
        if func == ff.var1:
            out_assigns.append((p.name, "next_val"))
        elif func == ff.var2:
            out_assigns.append((p.name, "~next_val"))
        elif func:
            # Try to map: if function is negation of var1
            neg = liberty_expr_to_verilog(func)
            out_assigns.append((p.name, neg.replace(ff.var1, "next_val").replace(ff.var2, "~next_val")))
        else:
            out_assigns.append((p.name, "next_val"))

    if ff.clear or ff.preset:
        # Async reset/set
        clear_expr = liberty_expr_to_verilog(ff.clear) if ff.clear else ""
        preset_expr = liberty_expr_to_verilog(ff.preset) if ff.preset else ""

        # Determine async signals for sensitivity list
        async_signals = []
        for p in inputs:
            if p.name in (ff.clear or "") or p.name in (ff.preset or ""):
                if f"~{p.name}" in clear_expr or f"~{p.name}" in preset_expr:
                    async_signals.append(f"negedge {p.name}")
                else:
                    async_signals.append(f"posedge {p.name}")

        sens = ", ".join([f"posedge {clk_expr}"] + async_signals)
        lines.append(f"    always @({sens}) begin")
        if preset_expr:
            lines.append(f"        if ({preset_expr})")
            # preset sets ff.var1 to 1
            for name, expr in out_assigns:
                val = expr.replace("next_val", "1'b1").replace("~1'b1", "1'b0")
                lines.append(f"            {name} <= {val};")
        if clear_expr:
            kw = "else if" if preset_expr else "if"
            lines.append(f"        {kw} ({clear_expr})")
            # clear sets ff.var1 to 0
            for name, expr in out_assigns:
                val = expr.replace("next_val", "1'b0").replace("~1'b0", "1'b1")
                lines.append(f"            {name} <= {val};")
        lines.append("        else begin")
        for name, expr in out_assigns:
            lines.append(f"            {name} <= {expr.replace('next_val', next_expr)};")
        lines.append("        end")
        lines.append("    end")
    else:
        lines.append(f"    always @(posedge {clk_expr}) begin")
        for name, expr in out_assigns:
            lines.append(f"        {name} <= {expr.replace('next_val', next_expr)};")
        lines.append("    end")

    lines.append("endmodule")
    return "\n".join(lines)


def generate_latch_verilog(cell: Cell) -> str:
    """Generate Verilator-compatible Verilog for a latch cell."""
    latch = cell.latch
    assert latch is not None

    outputs = [p for p in cell.pins if p.direction == "output"]
    inputs = [p for p in cell.pins if p.direction == "input"]

    port_names = [p.name for p in outputs] + [p.name for p in inputs]
    port_list = ", ".join(port_names)

    lines = []
    lines.append(f"module {cell.name} ({port_list});")

    for p in outputs:
        lines.append(f"    output reg {p.name};")
    for p in inputs:
        lines.append(f"    input {p.name};")
    lines.append("")

    enable_expr = liberty_expr_to_verilog(latch.enable)
    data_expr = liberty_expr_to_verilog(latch.data_in)

    # Map internal variable to output pin
    out_assigns = []
    for p in outputs:
        func = p.function
        if func == latch.var1:
            out_assigns.append((p.name, "data_val"))
        elif func == latch.var2:
            out_assigns.append((p.name, "~data_val"))
        elif func:
            neg = liberty_expr_to_verilog(func)
            out_assigns.append((p.name, neg.replace(latch.var1, "data_val").replace(latch.var2, "~data_val")))
        else:
            out_assigns.append((p.name, "data_val"))

    lines.append("    always_latch begin")
    lines.append(f"        if ({enable_expr})")
    for name, expr in out_assigns:
        lines.append(f"            {name} = {expr.replace('data_val', data_expr)};")
    lines.append("    end")

    lines.append("endmodule")
    return "\n".join(lines)


def generate_combinational_verilog(cell: Cell) -> str:
    """Generate Verilator-compatible Verilog for a combinational cell.

    Emits one `assign <out> = <expr>;` per output pin with a non-empty
    Liberty `function:` field. Output pins without `function:` (rare; mostly
    test/scan ports) are left undriven so Verilator infers them as wires —
    that is preferable to a fabricated value that can mask real bugs.
    """
    outputs = [p for p in cell.pins if p.direction == "output"]
    inputs = [p for p in cell.pins if p.direction == "input"]

    port_names = [p.name for p in outputs] + [p.name for p in inputs]
    port_list = ", ".join(port_names)

    lines = [f"module {cell.name} ({port_list});"]
    for p in outputs:
        lines.append(f"    output {p.name};")
    for p in inputs:
        lines.append(f"    input {p.name};")
    lines.append("")
    for p in outputs:
        if p.function:
            expr = liberty_expr_to_verilog(p.function)
            lines.append(f"    assign {p.name} = {expr};")
    lines.append("endmodule")
    return "\n".join(lines)


def generate_dff_v(cells: list[Cell]) -> str:
    """Generate complete behavioral Verilog content from parsed cells.

    Emits FF, latch and combinational cells. (Name kept for backwards
    compatibility with callers and tests.)
    """
    header = (
        "// Behavioral models for stdcells (compatible with Verilator).\n"
        "// Auto-generated from .lib by lib_to_verilog.py\n"
        "//\n"
        "// The original PDK models use Verilog-1995 UDP tables which are not\n"
        "// supported by Verilator. These are simple replacements.\n"
    )
    parts = [header]
    for cell in cells:
        if cell.ff:
            parts.append(generate_ff_verilog(cell))
        elif cell.latch:
            parts.append(generate_latch_verilog(cell))
        else:
            parts.append(generate_combinational_verilog(cell))
    return "\n\n".join(parts) + "\n"


def parse_lef_macros(text: str) -> set[str]:
    """Extract MACRO names from LEF text."""
    macros = set()
    for m in re.finditer(r"^MACRO\s+(\S+)", text, re.MULTILINE):
        macros.add(m.group(1))
    return macros


def generate_empty_v(lef_macros: set[str], lib_cells: set[str]) -> str:
    """Generate empty.v stubs for physical-only cells (in LEF but not in .lib)."""
    physical_only = sorted(lef_macros - lib_cells)
    if not physical_only:
        return ""
    header = (
        "// Empty module stubs for physical-only cells.\n"
        "// Auto-generated from .lef/.lib by lib_to_verilog.py\n"
        "//\n"
        "// These cells (filler, tap, decap, etc.) have no electrical behavior\n"
        "// but need stubs to silence simulation warnings.\n"
    )
    parts = [header]
    for name in physical_only:
        parts.append(f"module {name};\nendmodule")
    return "\n".join(parts) + "\n"


def read_file(path: str) -> str:
    """Read a file, decompressing .gz if needed."""
    if path.endswith(".gz"):
        with gzip.open(path, "rt") as f:
            return f.read()
    else:
        return Path(path).read_text()


def classify_files(paths: list[str]) -> tuple[list[str], list[str]]:
    """Classify files into .lib and .lef based on extension."""
    libs = []
    lefs = []
    for p in paths:
        if p.endswith(".lib") or p.endswith(".lib.gz"):
            libs.append(p)
        elif p.endswith(".lef"):
            lefs.append(p)
    return libs, lefs


def main():
    parser = argparse.ArgumentParser(
        description="Generate Verilator-compatible behavioral Verilog from Liberty .lib files"
    )
    # action="extend" so repeated `--lib FOO --lib BAR` accumulate; with the
    # default `store` action argparse silently keeps only the last invocation.
    parser.add_argument("--lib", nargs="+", action="extend", default=[],
                        help="Liberty .lib file(s) (may be .gz)")
    parser.add_argument("--lef", nargs="+", action="extend", default=[],
                        help="LEF file(s) for physical-only cell detection")
    parser.add_argument("--srcs", nargs="+", action="extend", default=[],
                        help="Mixed .lib/.lib.gz/.lef files (auto-classified)")
    parser.add_argument("--dff", required=True,
                        help="Output path for sequential cell behavioral models")
    parser.add_argument("--empty", required=True,
                        help="Output path for physical-only cell empty stubs")
    args = parser.parse_args()

    # Auto-classify --srcs by extension
    auto_libs, auto_lefs = classify_files(args.srcs)
    lib_paths = args.lib + auto_libs
    lef_paths = args.lef + auto_lefs

    if not lib_paths:
        parser.error("No .lib files provided (use --lib or --srcs)")

    # Parse all .lib files
    all_cells = []
    all_lib_cell_names = set()
    for lib_path in lib_paths:
        text = read_file(lib_path)
        cells = parse_lib_cells(text)
        all_cells.extend(cells)
        # Also collect all cell names (including non-sequential)
        for m in re.finditer(r"^\s*cell\s*\(\s*(\S+)\s*\)", text, re.MULTILINE):
            all_lib_cell_names.add(m.group(1))

    # Generate dff.v
    dff_content = generate_dff_v(all_cells)
    Path(args.dff).write_text(dff_content)

    # Parse LEF and generate empty.v
    lef_macros = set()
    for lef_path in lef_paths:
        text = Path(lef_path).read_text()
        lef_macros |= parse_lef_macros(text)
    empty_content = generate_empty_v(lef_macros, all_lib_cell_names)
    Path(args.empty).write_text(empty_content)


if __name__ == "__main__":
    main()
