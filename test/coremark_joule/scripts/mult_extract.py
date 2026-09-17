#!/usr/bin/env python3
"""Take one module out of a hardened netlist, with its delays.

5.2b measures glitch inside the multiplier by simulating that module on
its own. Nothing is re-synthesized: what is wanted is the module as the
design hardened it, so this cuts it out of the generated netlist and
cuts the matching subtree out of the SDF `write_sdf` wrote for the whole
design.

Four things come out, and each is needed by the replay:

- the module's own Verilog, so iverilog has something to instantiate;
- its port list with directions, widths and the netlist's own spelling
  -- escaped identifiers included, because a dump names a port
  unescaped and a netlist may not;
- its name, which is a yosys-uniquified mouthful nobody should retype;
- its SDF, with the instance paths rewritten relative to the module
  rather than to the design root, because that is what
  `$sdf_annotate(file, dut)` resolves against.

The cells the SDF does not mention are not an error: a tie cell has no
timing arc, so it has no entry. The count is reported rather than
checked, and 5.2b states it.
"""

import argparse
import re
import sys

PORT = re.compile(
    r'^\s*(input|output|inout)\s+(?:\[(\d+):(\d+)\]\s+)?(\\?\S+?)\s*;', re.M)
INSTANCE = re.compile(r'\(INSTANCE ([^)]*)\)')


def module_body(text, needle):
    """The text of the one module whose name contains `needle`."""
    starts = [m.start() for m in re.finditer(r'^module\s', text, re.M)]
    for start in starts:
        name = re.match(r'module\s+(\S+)', text[start:]).group(1)
        if needle in name:
            end = text.index("endmodule", start) + len("endmodule")
            return name, text[start:end]
    raise ValueError("no module name contains %r" % needle)


def ports(body):
    """(direction, name, width, spelling) in the order the netlist declares."""
    out = []
    for kind, hi, lo, raw in PORT.findall(body):
        width = (int(hi) - int(lo) + 1) if hi else 1
        out.append((kind, raw.lstrip("\\"), width, raw))
    return out


def cells(body):
    """Instance names of the cells in the module."""
    found = []
    for line in body.splitlines():
        m = re.match(r'\s*([A-Za-z_]\w*)\s+(\\?\S+?)\s*\(', line)
        if m and m.group(1) not in (
                "module", "input", "output", "inout", "wire", "assign"):
            found.append(m.group(2).lstrip("\\"))
    return found


def sdf_subtree(text, needle):
    """The SDF entries under the one instance path containing `needle`.

    The prefix is discovered rather than declared: it is whatever the
    matching entries agree on, and if they do not agree on one there is
    more than one instance of the module and the caller has to say which.
    """
    head = text[:text.index("(CELL")]
    blocks, i = [], 0
    while True:
        j = text.find("(CELL", i)
        if j < 0:
            break
        depth, k = 0, j
        while k < len(text):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        blocks.append(text[j:k + 1])
        i = k + 1

    kept, prefixes = [], set()
    for block in blocks:
        m = INSTANCE.search(block)
        if m and needle in m.group(1):
            kept.append(block)
            prefixes.add(m.group(1).rsplit("/", 1)[0])
    if not kept:
        raise ValueError("no SDF instance path contains %r" % needle)
    if len(prefixes) != 1:
        raise ValueError(
            "%r matches %d instance paths, need one: %s"
            % (needle, len(prefixes), sorted(prefixes)[:3]))
    prefix = prefixes.pop() + "/"
    kept = [b.replace("(INSTANCE " + prefix, "(INSTANCE ") for b in kept]
    return head + "\n".join(kept) + "\n)\n", len(kept), prefix


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--sdf", required=True)
    ap.add_argument("--module", required=True,
                    help="substring naming the module, e.g. ibex_multdiv_fast")
    ap.add_argument("--instance",
                    help="substring naming the module's instance path in the "
                         "SDF, e.g. multdiv_i. The SDF names instances and the "
                         "netlist names modules, and yosys does not spell the "
                         "two the same, so the caller says which rather than "
                         "the script guessing. Defaults to --module.")
    ap.add_argument("--out-verilog", required=True)
    ap.add_argument("--out-ports", required=True)
    ap.add_argument("--out-name", required=True)
    ap.add_argument("--out-sdf", required=True)
    args = ap.parse_args(argv)

    with open(args.netlist, errors="replace") as f:
        name, body = module_body(f.read(), args.module)
    with open(args.sdf, errors="replace") as f:
        sdf, n_cells, prefix = sdf_subtree(
            f.read(), args.instance or args.module)

    with open(args.out_verilog, "w") as f:
        f.write(body + "\n")
    with open(args.out_ports, "w") as f:
        for row in ports(body):
            f.write("%s %s %d %s\n" % row)
    with open(args.out_name, "w") as f:
        f.write(name + "\n")
    with open(args.out_sdf, "w") as f:
        f.write(sdf)

    in_module = cells(body)
    print("mult_extract: %s" % name)
    print("mult_extract: %d ports, %d cells in the module, %d with an SDF "
          "entry (%d have no timing arc)"
          % (len(ports(body)), len(in_module), n_cells,
             len(in_module) - n_cells))
    print("mult_extract: instance prefix %s" % prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
