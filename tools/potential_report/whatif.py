"""Tier 2 of the potential report: what a rewrite would buy, measured.

For a replicated leaf inside a parent, synthesises the parent twice with
yosys and ABC on generic gates:

- kept:      the leaf a module of its own (keep_hierarchy), as the flow
             synthesises it when the leaf is in SYNTH_KEEP_MODULES; a
             constant on a leaf port cannot propagate into it;
- flattened: the leaf dissolved into the parent; constants propagate
             and ABC can share logic across the copies.

The difference bounds what a rewrite that hands the copies their
constants (or shares their decode) buys, in gates and in logic levels.
Generic gates, not the library: the number ranks candidates, the flow's
own period decides.
"""

import argparse
import json
import re
import subprocess
import sys

GATES = "AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX"
# yosys's abc -g ignores -D (it reaches only liberty and LUT mapping), so
# the depth arm names its own script: choices, a level-minimising
# balance and a mapping to a delay target no network meets, on the unit
# delays of yosys's generic gate library.
DELAY_SCRIPT = " -script +strash;dch,-f;balance,-l;map,-D,1;topo"


def run(yosys, read, top, leaves, flatten, log, delay=False, plugins=()):
    keep = "".join("setattr -mod -set keep_hierarchy 1 %s; " % l for l in leaves)
    script = (
        read
        + "; hierarchy -top %s; " % top
        + ("" if flatten else keep)
        + "synth -top %s %s -run begin:fine; " % (top, "-flatten" if flatten else "")
        + "synth -top %s -run fine:check; " % top
        + "abc -g %s%s; opt_clean; " % (GATES, DELAY_SCRIPT if delay else "")
        + ("flatten; " if not flatten else "")
        + "tee -o %s.stat stat; tee -o %s.ltp ltp -noff" % (log, log)
    )
    cmd = [yosys]
    for p in plugins:
        cmd += ["-m", p]
    subprocess.run(cmd + ["-q", "-l", log, "-p", script], check=True)
    cells = None
    with open(log + ".stat") as f:
        for line in f:
            m = re.match(r"\s+(\d+)\s+cells$", line) or re.match(
                r"\s+Number of cells:\s+(\d+)", line
            )
            if m:
                cells = int(m.group(1))
    with open(log + ".ltp") as f:
        m = re.search(r"Longest topological path in \S+ \(length=(\d+)\)", f.read())
    return {"cells": cells, "levels": int(m.group(1)) if m else None}


STA_TCL = """
foreach lef {{{lefs}}} {{ read_lef $lef }}
foreach lib {{{libs}}} {{ read_liberty $lib }}
read_verilog {netlist}
link_design {top}
create_clock -name clk -period 10000 [get_ports clock]
set ins [delete_from_list [all_inputs] [get_ports clock]]
set_input_delay 0 -clock clk $ins
set_output_delay 0 -clock clk [all_outputs]
set_driving_cell -lib_cell BUFx4_ASAP7_75t_R $ins
set p [find_timing_paths -path_delay max -group_path_count 1]
puts [format "worst_ps %.1f" [expr {{10000.0 - [get_property [lindex $p 0] slack]}}]]
"""


def run_lib(
    yosys, openroad, read, top, leaves, flatten, log, libs, seq_lib, lefs, plugins=()
):
    """The arm mapped to the library and timed by OpenSTA: fanout loads
    from the liberty pin capacitances, no wire. Unit gate levels cannot
    see fanout, and fanout is what a shared decode removes."""
    keep = "".join("setattr -mod -set keep_hierarchy 1 %s; " % l for l in leaves)
    netlist = log + ".v"
    script = (
        read
        + "; hierarchy -top %s; " % top
        + ("" if flatten else keep)
        + "synth -top %s %s -run begin:fine; " % (top, "-flatten" if flatten else "")
        + "synth -top %s -run fine:check; " % top
        + "dfflibmap -liberty %s; " % seq_lib
        + "abc %s -D 100; opt_clean; " % " ".join("-liberty %s" % l for l in libs)
        + "flatten; hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L; "
        + "setundef -zero; opt_clean -purge; "
        + "tee -o %s.stat stat; write_verilog -noattr -noexpr %s" % (log, netlist)
    )
    cmd = [yosys]
    for p in plugins:
        cmd += ["-m", p]
    subprocess.run(cmd + ["-q", "-l", log, "-p", script], check=True)
    cells = None
    with open(log + ".stat") as f:
        for line in f:
            m = re.match(r"\s+(\d+)\s+cells$", line) or re.match(
                r"\s+Number of cells:\s+(\d+)", line
            )
            if m:
                cells = int(m.group(1))
    tcl = log + ".sta.tcl"
    with open(tcl, "w") as f:
        f.write(
            STA_TCL.format(
                lefs=" ".join(lefs),
                libs=" ".join(libs + [seq_lib]),
                netlist=netlist,
                top=top,
            )
        )
    out = subprocess.run(
        [openroad, "-exit", "-no_init", "-no_splash", tcl],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    m = re.search(r"worst_ps ([-0-9.]+)", out)
    return {"cells": cells, "worst_ps": float(m.group(1)) if m else None}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yosys", required=True)
    p.add_argument(
        "--read", required=True, help="yosys command(s) that read the design"
    )
    p.add_argument("--top", required=True)
    p.add_argument(
        "--leaf", action="append", required=True, help="module kept in the 'kept' arm"
    )
    p.add_argument("--log", required=True, help="log file prefix")
    p.add_argument(
        "--plugin", action="append", default=[], help="yosys plugin to load (slang.so)"
    )
    p.add_argument("--out", help="result JSON (default: stdout)")
    p.add_argument(
        "--mapping",
        action="append",
        choices=["area", "delay", "lib"],
        help="arms (default area and delay)",
    )
    p.add_argument(
        "--openroad", help="for the lib arm: OpenSTA times the mapped netlist"
    )
    p.add_argument(
        "--liberty",
        action="append",
        default=[],
        help="for the lib arm: combinational libraries",
    )
    p.add_argument("--seq-liberty", help="for the lib arm: the flip-flop library")
    p.add_argument(
        "--lef",
        action="append",
        default=[],
        help="for the lib arm: technology then cell LEF",
    )
    args = p.parse_args(argv)
    args.mapping = args.mapping or ["area", "delay"]
    result = {"top": args.top, "leaf": args.leaf}
    for mapping in args.mapping:
        if mapping == "lib":
            arms = {}
            for name, flatten in (("kept", False), ("flattened", True)):
                arms[name] = run_lib(
                    args.yosys,
                    args.openroad,
                    args.read,
                    args.top,
                    args.leaf,
                    flatten,
                    "%s.lib.%s" % (args.log, name),
                    args.liberty,
                    args.seq_liberty,
                    args.lef,
                    args.plugin,
                )
            k, f = arms["kept"], arms["flattened"]
            if k["cells"] and f["cells"] is not None:
                arms["cells_saved_pct"] = round(
                    100.0 * (1 - f["cells"] / k["cells"]), 1
                )
            if k["worst_ps"] is not None and f["worst_ps"] is not None:
                arms["worst_ps_saved"] = round(k["worst_ps"] - f["worst_ps"], 1)
            result["lib"] = arms
            continue
        delay = mapping == "delay"
        kept = run(
            args.yosys,
            args.read,
            args.top,
            args.leaf,
            False,
            "%s.%s.kept" % (args.log, mapping),
            delay,
            args.plugin,
        )
        flat = run(
            args.yosys,
            args.read,
            args.top,
            args.leaf,
            True,
            "%s.%s.flat" % (args.log, mapping),
            delay,
            args.plugin,
        )
        r = {"kept": kept, "flattened": flat}
        if kept["cells"] and flat["cells"] is not None:
            r["cells_saved_pct"] = round(100.0 * (1 - flat["cells"] / kept["cells"]), 1)
        if kept["levels"] and flat["levels"] is not None:
            r["levels_saved"] = kept["levels"] - flat["levels"]
        result[mapping] = r
    text = json.dumps(result, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
