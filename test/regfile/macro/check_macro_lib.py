"""A register file built as a macro of its own presents a clocked macro.

Reads the macro's liberty from its abstract and checks what a parent
needs from it: a clock pin of buffer scale, not the register file's whole
clock net (mode macro's model was 8.5 pF for this register file), and
the macro's clock tree in its model (min/max_clock_tree_path), which the
parent's CTS balances against.

    check_macro_lib.py <abstract files...>
"""

import re
import sys


def _arcs(text, kind):
    """The values of every `kind` timing arc in a liberty."""
    out = []
    for m in re.finditer(
        r'timing_type\s*:\s*"?' + kind + r'"?\s*;(.*?)\}\s*\}', text, re.S
    ):
        for row in re.findall(r'values\s*\(\s*"([^"]*)"', m.group(1)):
            out += [float(v) for v in row.split(",") if v.strip()]
    return out


def main():
    libs = [p for p in sys.argv[1:] if p.endswith(".lib")]
    if len(libs) != 1:
        sys.exit(f"want one .lib among the abstract's files, got {sys.argv[1:]}")
    text = open(libs[0]).read()
    pin = re.search(r'pin\s*\(\s*"?clock"?\s*\)\s*\{(.*?)\}', text, re.S)
    if not pin:
        sys.exit("no clock pin in the macro's liberty")
    cap = float(re.search(r"\bcapacitance\s*:\s*([\d.eE+-]+)", pin.group(1)).group(1))
    # buffer scale: a clock buffer's input is a few fF; 64 x 256 flops
    # unbuffered are thousands
    if cap > 100:
        sys.exit(f"clock pin {cap} fF: the register file's clock net is not buffered")
    lo, hi = _arcs(text, "min_clock_tree_path"), _arcs(text, "max_clock_tree_path")
    if not lo or not hi:
        sys.exit(
            "no min/max_clock_tree_path: the macro's clock tree is not in its model"
        )
    if not (0 < min(lo) <= max(hi)):
        sys.exit(f"clock tree path min {min(lo)} max {max(hi)}: not a built tree")
    print(f"clock pin {cap} fF, clock tree {min(lo):.0f}..{max(hi):.0f}")


if __name__ == "__main__":
    main()
