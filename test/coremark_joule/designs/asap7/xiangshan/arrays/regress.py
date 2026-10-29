"""The loop a front-end change goes through on a block, cheapest first:

1. extracted with the index comparisons kept in the cell, proven equal
   to the block, and the negative control proven different;
2. extracted as the flows build it (decoded once), written as Verilog as
   the extraction's genrule writes it, and read back through yosys's
   `check -assert`: a netlist synthesis would refuse (two drivers on a
   wire) fails here in seconds, not in the flow;
3. with --direct, the decoded extraction proven equal directly (the
   Rob's takes over an hour; the smaller blocks minutes).

    bazelisk run //test/coremark_joule/designs/asap7/xiangshan/arrays:regress -- \\
        <yosys> <proc.json> <module> <workdir> [--direct]

<proc.json> is the block's `<module>_proc_json` output, copied somewhere
writable; paths absolute. Stops at the first step that fails; when a
proof says NOT equivalent, localise.py names the outputs that differ.
"""

import json
import os
import subprocess
import sys

import check

HERE = os.path.dirname(os.path.abspath(__file__))


def step(name, args):
    # under Bazel the interpreter runs with PYTHONSAFEPATH, so a script
    # does not see the modules beside it unless told
    r = subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        cwd=HERE,
        env=dict(os.environ, PYTHONPATH=HERE),
    )
    print(f"regress: {name}: {'ok' if r.returncode == 0 else 'FAILED'}", flush=True)
    if r.returncode:
        sys.exit((r.stdout + r.stderr)[-3000:])
    return r.stdout


def blackboxes(design):
    """Verilog stubs of a design's blackbox modules, from their ports."""
    out = []
    for name, mod in design["modules"].items():
        if "blackbox" not in mod.get("attributes", {}):
            continue
        ports = [
            f"{p['direction']} [{len(p['bits']) - 1}:0] {n}"
            for n, p in mod["ports"].items()
        ]
        out.append(f"(* blackbox *) module {name}({', '.join(ports)});\nendmodule\n")
    return "".join(out)


def main(argv):
    yosys, proc, module, work = argv[1:5]
    direct = "--direct" in argv[5:]
    # the extraction's own options (extract.py --firtool-vectors)
    opts = [a for a in argv[5:] if a != "--direct"]
    os.makedirs(work, exist_ok=True)
    kept = os.path.join(work, "kept.json")
    decoded = os.path.join(work, "decoded.json")
    step("extract, index kept", ["extract.py", proc, module, kept, "--keep-idx"] + opts)
    step("proof, index kept", ["check.py", yosys, proc, kept, module])
    step("control, must differ", ["check.py", yosys, proc, kept, module, "mutate"])
    out = step("extract, decoded", ["extract.py", proc, module, decoded] + opts)
    print(out.strip().splitlines()[-1])
    verilog = os.path.join(work, "decoded.v")
    rc, log = check.run(
        yosys,
        f"read_json {decoded}; hierarchy -top {module}; opt_dff; "
        f"write_verilog -noattr {verilog}",
    )
    if not rc:
        # the blackboxes (register files, kept buffers) as stubs, which
        # write_verilog leaves out: the core defines them in the flow
        stubs = os.path.join(work, "blackboxes.v")
        with open(stubs, "w") as f:
            f.write(blackboxes(json.load(open(decoded))))
        rc, log = check.run(
            yosys,
            f"read_verilog {stubs}; read_verilog {verilog}; hierarchy -top {module}; "
            "proc; check -assert",
        )
    print(f"regress: Verilog read back: {'ok' if rc == 0 else 'FAILED'}")
    if rc:
        sys.exit(log[-3000:])
    if direct:
        step("proof, decoded", ["check.py", yosys, proc, decoded, module])


if __name__ == "__main__":
    main(sys.argv)
