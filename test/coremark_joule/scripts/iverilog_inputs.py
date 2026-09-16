"""Make a generated netlist and its SDF readable by iverilog.

Two transformations, both working around what iverilog's SDF reader
cannot take, and neither changing what is being measured.

**Names with dots.**

OpenROAD names clock-tree cells after the pin they drive, so an instance
is called `clkbuf_3_7_0_u_core.clk` -- a name with the hierarchy
separator inside it. Verilog escapes that (`\\clkbuf_..._u_core.clk `)
and OpenSTA's SDF escapes it too (`clkbuf_..._u_core\\.clk`), both
correctly. iverilog's SDF reader does not honour the escape: it splits
on the dot, looks for a child instance called `clk`, and reports
"Cannot find ... in scope". On ibex that is 96.2 % of instances, so
almost nothing gets a delay -- and the run still finishes, producing a
zero-delay answer wearing an annotated run's name.

This is the same shape as the SAIF's hierarchy separator (5.12) and the
same remedy: the name is not the measurement. Both files are generated
from one ODB, so both can be rewritten by one rule, and the simulation
only requires that they agree.

**Conditional delays.** OpenSTA writes state-dependent arcs as
`(COND <expr> (IOPATH ...))`, and iverilog rejects the construct, then
stops annotating entirely -- "Too many errors: syntax error" -- so a
handful of unreadable entries costs the whole file. The unconditional
IOPATH for the same pin pair is written alongside every one of them, so
dropping the COND blocks keeps the delay OpenSTA already stated and
loses only its state-dependent refinement.

Neither is a patch to iverilog: upstream repositories are read-only here
(CLAUDE.md), and rewriting our own generated files is smaller than a
simulator change anyway.
"""

import argparse
import re
import sys

# A Verilog escaped identifier: backslash, then anything up to whitespace.
_VERILOG_ESCAPED = re.compile(r"\\(\S+)")
# An SDF instance path, where a literal dot in a name is backslash-escaped.
_SDF_INSTANCE = re.compile(r"\(INSTANCE ([^)]*)\)")

REPLACEMENT = "__dot__"


def safe(name):
    """The name with dots replaced, so no reader can mistake one for a path."""
    return name.replace(".", REPLACEMENT)


def rewrite_verilog(text):
    """Rename escaped identifiers that contain a dot.

    An escaped identifier without a dot is left exactly as it was: the
    netlist has thousands of them and rewriting those would be churn
    with no purpose.
    """
    n = [0]

    def sub(m):
        name = m.group(1)
        if "." not in name:
            return m.group(0)
        n[0] += 1
        return "\\" + safe(name)

    return _VERILOG_ESCAPED.sub(sub, text), n[0]


def rewrite_sdf(text):
    """Rename SDF instance paths whose components contain an escaped dot.

    `a\\.b/c` is one component `a.b` inside instance `c`: the escaped dot
    is part of a name and the unescaped slash is the divider. Only the
    escaped ones are rewritten.
    """
    n = [0]

    def sub(m):
        path = m.group(1)
        if "\\." not in path:
            return m.group(0)
        n[0] += 1
        return "(INSTANCE %s)" % path.replace("\\.", REPLACEMENT)

    return _SDF_INSTANCE.sub(sub, text), n[0]


def _drop_blocks(text, opener):
    """Remove every `(<opener> ...)` block, parenthesis-aware.

    Line-based removal leaves half a block behind, which is a syntax
    error rather than a lost entry -- and iverilog abandons the whole
    file on one of those, so a careless filter costs every delay in it.
    """
    out, i, n = [], 0, 0
    while True:
        j = text.find("(" + opener, i)
        if j < 0:
            out.append(text[i:])
            return "".join(out), n
        out.append(text[i:j])
        depth, k = 0, j
        while k < len(text):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        n += 1
        i = k + 1


def drop_timingcheck(text):
    """Remove `(TIMINGCHECK ...)` sections.

    They carry setup, hold and pulse-width *constraints*, not
    propagation delays, so nothing measurable is lost. iverilog cannot
    parse the form OpenSTA writes and gives up on the file when it meets
    one. They would also be unwelcome if they did parse: a violated
    check drives X into the design, and this measurement is about
    transitions rather than about whether the netlist meets timing --
    that question is 3.8's, answered by static analysis.
    """
    return _drop_blocks(text, "TIMINGCHECK")


def drop_celltypes(text, celltypes):
    """Remove `(CELL ...)` blocks whose CELLTYPE is one of `celltypes`.

    The memories are the case. They are behavioural models standing in
    for hardened macros, and OpenSTA writes their read delay as
    `(IOPATH clk rd_out[0] ...)` -- a bit-select destination iverilog
    rejects, on a model that declares no path for it to land on anyway.
    Their energy comes from Liberty rather than from this simulation
    (3.4), so dropping the block loses no measurement.

    What it does lose is stated rather than hidden: memory read data
    then arrives at time zero instead of 218 ps, so the logic consuming
    it sees one fewer late-arriving input, and the glitch this measures
    is biased low for that reason as well as for the missing
    interconnect delays.
    """
    out, i, n = [], 0, 0
    while True:
        j = text.find("(CELL", i)
        if j < 0:
            out.append(text[i:])
            return "".join(out), n
        depth, k = 0, j
        while k < len(text):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        block = text[j:k + 1]
        if any('(CELLTYPE "%s")' % c in block for c in celltypes):
            out.append(text[i:j])
            n += 1
        else:
            out.append(text[i:k + 1])
        i = k + 1


def drop_cond(text):
    """Remove `(COND ... )` blocks, keeping the unconditional arcs."""
    return _drop_blocks(text, "COND")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verilog", nargs=2, metavar=("IN", "OUT"))
    ap.add_argument("--sdf", nargs=2, metavar=("IN", "OUT"))
    ap.add_argument(
        "--drop-celltype",
        action="append",
        default=[],
        help="CELLTYPE whose blocks to remove; repeatable. For models "
        "that declare no timing paths, such as the memories.",
    )
    args = ap.parse_args(argv)
    if args.verilog:
        src, dst = args.verilog
        text, n = rewrite_verilog(open(src, errors="replace").read())
        open(dst, "w").write(text)
        print("iverilog_inputs: renamed %d escaped identifiers in the netlist" % n)
    if args.sdf:
        src, dst = args.sdf
        text, n = rewrite_sdf(open(src, errors="replace").read())
        text, c = drop_cond(text)
        text, tc = drop_timingcheck(text)
        text, dc = drop_celltypes(text, args.drop_celltype)
        open(dst, "w").write(text)
        print(
            "iverilog_inputs: renamed %d instance paths, dropped %d "
            "conditional arcs, %d timing-check sections and %d cells by "
            "type in the SDF" % (n, c, tc, dc)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
