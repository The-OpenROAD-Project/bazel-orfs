"""Decode once: a cell instanced N times, each with its own constant index,
that compares the index against inputs every instance shares, becomes one
index-free cell and N-wide decoders in the parent.

A cell array written that way (XiangShan's RobEntryCell, SqEntryCell)
has every instance compare its constant index against the same buses:
N copies of a decoder ABC never sees as one, and a constant per instance
that uniquifies the cell, so synthesis maps it N times. Here each
comparison of the index in the cell,

    X == idx   idx == X   idx > X   idx >= X   idx < X   idx <= X

with X an input port of the cell or a slice of one, becomes an input bit
of the cell, io_decodeOnce_hits[k]; the parent computes each comparison
once for all N instances (a one-hot shift for ==, a thermometer for the
orders) and hands instance i bit i. The cell then has no index and every
instance is the same module.

It stops on any shape it does not recognise: the index used other than
in those comparisons, an X that is not a cell input, an instance whose
index is not a constant, or instances that connect X's port differently.
No register is added and none is removed.

    decode_once.py <in.sv> <out.sv> <cell> <index port> <parent>
"""

import re
import sys

_OPS = {
    # op as written with the index on the left, and its mirror
    "==": "==",
    ">": "<",
    ">=": "<=",
    "<": ">",
    "<=": ">=",
}


def _module(text, name):
    m = re.search(r"^module " + name + r"\b", text, re.M)
    if not m:
        sys.exit(f"decode_once: no module {name}")
    end = text.index("\nendmodule", m.start()) + len("\nendmodule")
    return m.start(), end


def _inputs(cell):
    """The cell's input ports: name -> width."""
    header = cell[: cell.index(");")]
    ports = {}
    direction, width = None, 1
    for m in re.finditer(
        r"(input|output)?\s*(?:\[(\d+):(\d+)\])?\s*(\w+)\s*[,)\n]",
        header[header.index("(") :],
    ):
        if m.group(1):
            direction = m.group(1)
            width = int(m.group(2)) - int(m.group(3)) + 1 if m.group(2) else 1
        elif m.group(2):
            width = int(m.group(2)) - int(m.group(3)) + 1
        if direction == "input":
            ports[m.group(4)] = width
    return ports


def rewrite_cell(cell, idx, width):
    """The cell with every comparison of idx replaced by a hit input:
    (new cell text, [(op, port, slice)] in hit order)."""
    inputs = _inputs(cell)
    operand = r"(\w+)(\[\d+:\d+\]|\[\d+\])?"
    pat = re.compile(
        r"\b" + operand + r"\s*(==|>=|<=|>|<)\s*" + idx + r"\b"
        r"|\b" + idx + r"\s*(==|>=|<=|>|<)\s*" + operand
    )
    hits = []
    index = {}

    def sub(m):
        if m.group(1):
            port, sl, op = m.group(1), m.group(2) or "", _OPS[m.group(3)]
        else:
            op, port, sl = m.group(4), m.group(5), m.group(6) or ""
        if port not in inputs or port == idx:
            sys.exit(
                f"decode_once: {idx} compared with {port}{sl}, not an input of the cell"
            )
        key = (op, port, sl)
        if key not in index:
            index[key] = len(hits)
            hits.append(key)
        return f"io_decodeOnce_hits[{index[key]}]"

    body_start = cell.index(");") + 2
    head, body = cell[:body_start], cell[body_start:]
    body = pat.sub(sub, body)
    if re.search(r"\b" + idx + r"\b", body):
        line = next(l for l in body.splitlines() if re.search(r"\b" + idx + r"\b", l))
        sys.exit(f"decode_once: {idx} used other than in a comparison: {line.strip()}")
    if not hits:
        sys.exit(f"decode_once: {idx} is compared with nothing")
    # the index port becomes the hits port
    head, n = re.subn(
        r"input\s*\[" + str(width - 1) + r":0\]\s*" + idx + r"\b",
        f"input  [{len(hits) - 1}:0] io_decodeOnce_hits",
        head,
    )
    if n != 1:
        sys.exit(f"decode_once: no input [{width - 1}:0] {idx} in the cell's header")
    return head + body, hits


def rewrite_parent(parent, cell, idx, hits, width):
    inst = re.compile(r"^(  " + cell + r" (\w+) \()(.*?)(\n  \);)", re.M | re.S)
    found = list(inst.finditer(parent))
    if not found:
        sys.exit(f"decode_once: the parent instances no {cell}")
    conns, consts = [], []
    for m in found:
        ports = dict(
            re.findall(r"\.(\w+)\s*\(([^()]*(?:\([^()]*\))?[^()]*)\)", m.group(3))
        )
        c = re.fullmatch(r"\s*(\d+)'h([0-9A-Fa-f]+)\s*", ports.get(idx, ""))
        if not c:
            sys.exit(f"decode_once: {m.group(2)}'s {idx} is not a constant")
        consts.append(int(c.group(2), 16))
        conns.append(ports)
    n = len(found)
    if sorted(consts) != list(range(n)):
        sys.exit(f"decode_once: the {n} {cell} indices are not 0..{n - 1}")
    lines = [
        f"  // decode_once: {cell}'s {idx} comparisons, once for its {n} instances"
    ]
    for k, (op, port, sl) in enumerate(hits):
        srcs = {c[port].strip() for c in conns}
        if len(srcs) != 1:
            sys.exit(f"decode_once: the instances connect {port} differently")
        x = (
            f"{srcs.pop()}{sl}"
            if re.fullmatch(r"\w+", next(iter({c[port].strip() for c in conns})))
            else None
        )
        if x is None:
            sys.exit(f"decode_once: {port} is connected to an expression, not a net")
        w = n + 1
        one, ones = f"{w}'h1", f"{{{w}{{1'b1}}}}"
        expr = {
            "==": f"{one} << {x}",
            ">": f"{ones} << ({w}'({x}) + {w}'h1)",
            ">=": f"{ones} << {x}",
            "<": f"~({ones} << {x})",
            "<=": f"~({ones} << ({w}'({x}) + {w}'h1))",
        }[op]
        # bit i is the comparison for index i: idx == x, idx > x, ...
        lines.append(f"  wire [{w - 1}:0] _decodeOnce_{cell}_{k} = {expr};")
    text = parent
    for m, c in sorted(zip(found, consts), key=lambda mc: -mc[0].start()):
        hit = ", ".join(
            f"_decodeOnce_{cell}_{k}[{c}]" for k in reversed(range(len(hits)))
        )
        body = re.sub(
            r"\." + idx + r"\s*\([^)]*\)",
            f".io_decodeOnce_hits ({{{hit}}})",
            m.group(3),
        )
        text = text[: m.start()] + m.group(1) + body + m.group(4) + text[m.end() :]
    first = inst.search(text).start()
    return text[:first] + "\n".join(lines) + "\n" + text[first:]


def main(argv):
    src, out, cell, idx, parent = argv[1:6]
    text = open(src).read()
    s, e = _module(text, cell)
    cell_text = text[s:e]
    width = _inputs(cell_text).get(idx)
    if width is None:
        sys.exit(f"decode_once: {cell} has no input {idx}")
    new_cell, hits = rewrite_cell(cell_text, idx, width)
    text = text[:s] + new_cell + text[e:]
    s, e = _module(text, parent)
    text = text[:s] + rewrite_parent(text[s:e], cell, idx, hits, width) + text[e:]
    with open(out, "w") as f:
        f.write(text)
    print(
        f"decode_once: {cell}: {len(hits)} comparisons of {idx} decoded once in {parent}"
    )


if __name__ == "__main__":
    main(sys.argv)
