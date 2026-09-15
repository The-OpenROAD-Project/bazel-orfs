#!/usr/bin/env python3
"""Report the module closure of a top module in a split-Verilog directory.

firtool emits one file per module, so "how big is XSCore" is answerable
before synthesis: walk the instantiations from the top and add up what is
reachable. That separates the design being hardened from everything
elaborated around it, which for this study is most of what was written.

The parse is deliberately crude -- a module header, then identifiers in
instantiation position -- because it only has to be right about which
files are reachable, and a false positive costs an over-estimate rather
than a wrong answer.
"""

import argparse
import json
import os
import re
import sys

# `Foo foo_inst (` or `Foo #(...) foo_inst (`, at the start of a line.
_INSTANCE = re.compile(
    r"^\s{2,}([A-Za-z_][A-Za-z_0-9$]*)\s+(?:#\([^;]*?\)\s*)?[A-Za-z_]"
)
_MODULE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z_0-9$]*)")

# Keywords that appear in instantiation position but are not modules.
_NOT_A_MODULE = frozenset("""
    always always_comb always_ff always_latch and assign assert assume automatic
    begin buf bufif0 bufif1 case casex casez cmos default defparam disable else
    end endcase endfunction endgenerate endmodule endtask for force forever fork
    function generate genvar if initial inout input integer localparam logic
    macromodule module nand negedge nmos nor not notif0 notif1 or output parameter
    pmos posedge pulldown pullup reg release repeat return rtran rtranif0 rtranif1
    signed supply0 supply1 task time tran tranif0 tranif1 tri typedef unsigned var
    wait wand while wire wor xnor xor
    """.split())


def module_files(directory):
    """Map module name -> file path, from the module headers in each file."""
    found = {}
    for name in os.listdir(directory):
        if not name.endswith((".v", ".sv")):
            continue
        path = os.path.join(directory, name)
        with open(path, errors="replace") as f:
            for line in f:
                m = _MODULE.match(line)
                if m:
                    found[m.group(1)] = path
    return found


def instantiated(path):
    names = set()
    with open(path, errors="replace") as f:
        for line in f:
            m = _INSTANCE.match(line)
            if m and m.group(1) not in _NOT_A_MODULE:
                names.add(m.group(1))
    return names


def closure(directory, top):
    index = module_files(directory)
    if top not in index:
        raise SystemExit(
            "module_closure: no module {} in {} ({} modules found)".format(
                top, directory, len(index)
            )
        )

    seen, pending = set(), [top]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(
            n for n in instantiated(index[name]) if n in index and n not in seen
        )

    files = sorted({index[n] for n in seen})
    lines = 0
    size = 0
    for path in files:
        size += os.path.getsize(path)
        with open(path, errors="replace") as f:
            lines += sum(1 for _ in f)

    return {
        "top": top,
        "modules_in_directory": len(index),
        "modules_reachable": len(seen),
        "files_reachable": len(files),
        "bytes": size,
        "lines": lines,
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--top", required=True)
    parser.add_argument("--out")
    args = parser.parse_args(argv[1:])

    report = closure(args.directory, args.top)
    text = (
        "module closure of {top}\n"
        "  modules in directory : {modules_in_directory}\n"
        "  modules reachable    : {modules_reachable}\n"
        "  files reachable      : {files_reachable}\n"
        "  lines                : {lines:,}\n"
        "  bytes                : {bytes:,}\n"
    ).format(**report)
    sys.stdout.write(text)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
