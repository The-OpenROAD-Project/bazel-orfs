"""Surgery on XiangShan's Rob: its 352 RobEntryCells become one generated
RobEntryArray (rob_array_gen.py), every channel decoded once.

RobEntryCell must be exactly RobEntryCell.expected.sv, the cell the
generator was written from, and Rob must instance it 352 times as firtool
did, each cell on the shared robEntryCellInBits with its own constant
index; anything else stops the surgery. The cells' outputs keep their
wires, _robEntryCells_<i>_io_entry, so the rest of Rob is untouched. No
register is added: the array holds the cells' registers.

    rob_surgery.py <in.sv> <RobEntryCell.expected.sv> <out.sv>
"""

import re
import sys

ENTRIES = 352
ENTRY_BITS = 31

_CELL = re.compile(
    r"  RobEntryCell robEntryCells_(\d+) \(\s*"
    r"\.clock\s*\(clock\),\s*"
    r"\.reset\s*\(reset\),\s*"
    r"\.io_idx\s*\(9'h([0-9A-F]+)\),\s*"
    r"\.io_in\s*\(robEntryCellInBits\),\s*"
    r"\.io_entry\s*\(_robEntryCells_(\d+)_io_entry\)\s*"
    r"\);\n"
)


def _module(text, name):
    m = re.search(r"^module " + name + r"\b", text, re.M)
    if not m:
        sys.exit(f"rob_surgery: no module {name}")
    end = text.index("\nendmodule", m.start()) + len("\nendmodule")
    return m.start(), end


def surgery(text, expected):
    s, e = _module(text, "RobEntryCell")
    if text[s:e] != expected.rstrip("\n"):
        sys.exit(
            "rob_surgery: RobEntryCell is not the cell rob_array_gen.py implements"
        )
    s, e = _module(text, "Rob")
    rob = text[s:e]
    cells = list(_CELL.finditer(rob))
    if len(cells) != ENTRIES:
        sys.exit(
            f"rob_surgery: {len(cells)} RobEntryCell instances in Rob, not {ENTRIES}"
        )
    for m in cells:
        i, idx, out = int(m.group(1)), int(m.group(2), 16), int(m.group(3))
        if not i == idx == out:
            sys.exit(f"rob_surgery: robEntryCells_{i} has index {idx}, output {out}")
    if sorted(int(m.group(1)) for m in cells) != list(range(ENTRIES)):
        sys.exit("rob_surgery: the cells are not entries 0..351")
    if re.search(r"\bRobEntryCell\b", _CELL.sub("", rob)):
        sys.exit("rob_surgery: Rob uses RobEntryCell other than as the 352 cells")
    array = [
        f"  wire [{ENTRIES * ENTRY_BITS - 1}:0] _robEntryArray_io_entries;\n",
        "  RobEntryArray robEntryArray (\n"
        "    .clock      (clock),\n"
        "    .reset      (reset),\n"
        "    .io_in      (robEntryCellInBits),\n"
        "    .io_entries (_robEntryArray_io_entries)\n"
        "  );\n",
    ] + [
        f"  assign _robEntryCells_{i}_io_entry ="
        f" _robEntryArray_io_entries[{i * ENTRY_BITS} +: {ENTRY_BITS}];\n"
        for i in range(ENTRIES)
    ]
    first = cells[0].start()
    out = rob[:first] + "".join(array) + _CELL.sub("", rob[first:])
    return text[:s] + out + text[e:]


def main(argv):
    text = open(argv[1]).read()
    expected = open(argv[2]).read()
    with open(argv[3], "w") as f:
        f.write(surgery(text, expected))


if __name__ == "__main__":
    main(sys.argv)
