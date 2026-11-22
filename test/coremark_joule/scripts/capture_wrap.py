#!/usr/bin/env python3
"""Wrap each unit of an RTL simulation so its ports alone can be traced.

    capture_wrap.py IN.sv OUT.sv [--unit MODULE]... [--top TOP --path PATH]...

The replay of a power shard (scripts/replay_gen.py) drives one unit's
netlist alone from what the unit's ports did in one RTL simulation of
the whole design, the capture. A trace of the unit's scope would carry
every signal of its RTL module, not its ports alone. So each unit's RTL
module U is renamed U__rtl, and a module U with U's own port declarations
takes its place: it instantiates U__rtl as `rtl` and holds nothing but
its ports. A trace configuration that turns tracing on for the wrapper's
scope alone (`tracing_on -scope "<path>" -levels 1`) then records the
unit's ports and nothing else, and the unit's RTL is one level further
down, at <path>.rtl.

A unit is named by its module (--unit) or by its instance path below
--top (--path, `/` between instance names), which is how a simulation
shard cut out of a unit is declared.

Refused, by name: a unit with no module in IN, a path that names no
module instance, or a non-ANSI header (a port list without its
declarations).
"""

import argparse
import re
import sys

sys.path.insert(
    0, __import__("os").path.dirname(__import__("os").path.abspath(__file__))
)

from gate_stitch import check_pins, ports  # noqa: E402
from replay_gen import module_at  # noqa: E402


def _module_span(text, name):
    m = re.search(
        r"^(\s*module\s+)"
        + re.escape(name)
        + r"(\s*(?:#\s*\(.*?\)\s*)?\()(.*?)(\)\s*;)(.*?)^\s*endmodule\b[^\n]*\n?",
        text,
        re.M | re.S,
    )
    if not m:
        raise ValueError("no module {}".format(name))
    return m


def wrap(text, units):
    """`text` with each module in `units` behind a wrapper of its ports."""
    for unit in units:
        m = _module_span(text, unit)
        header = m.group(3)
        if not re.search(r"\b(input|output|inout)\b", header):
            raise ValueError("{}: a header without its port declarations".format(unit))
        names = sorted(ports(m.group(0)))
        wrapper = "module {}{}{}{}\n  {}__rtl rtl ({});\nendmodule\n".format(
            unit,
            m.group(2),
            header,
            m.group(4),
            unit,
            ", ".join(".{0}({0})".format(n) for n in names),
        )
        renamed = text[m.start() : m.end()].replace(
            m.group(1) + unit, m.group(1) + unit + "__rtl", 1
        )
        text = text[: m.start()] + renamed + wrapper + text[m.end() :]
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rtl")
    parser.add_argument("out")
    parser.add_argument("--unit", action="append", default=[])
    parser.add_argument("--top")
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args(argv)
    with open(args.rtl) as f:
        text = f.read()
    try:
        units = list(args.unit)
        for path in args.path:
            module = module_at(text, args.top, path)
            if module is None:
                raise ValueError(
                    "{}/{}: no module instance there".format(args.top, path)
                )
            units.append(module)
        text = wrap(text, sorted(set(units), key=units.index))
        # every wrapper's ports are its module's: checked, not assumed
        mods = [
            m.group(0)
            for m in re.finditer(
                r"^\s*module\s+\S+.*?^\s*endmodule\b[^\n]*\n?", text, re.M | re.S
            )
        ]
        _, refused, _ = check_pins(mods)
        if refused:
            raise ValueError("; ".join(refused[:20]))
    except ValueError as e:
        sys.stderr.write("capture_wrap: {}\n".format(e))
        return 1
    with open(args.out, "w") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
