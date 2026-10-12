"""coralnpu's LsuV1 as the snapshot has it and as surgery.py
--address-register leaves it, each with the modules it instantiates,
renamed so that both simulate in one binary:

    lsu_ref.v    the snapshot's LsuV1, modules suffixed _ref
    lsu_exmem.v  the surgered LsuV1, modules suffixed _exmem
    lsu_bad.v    the surgered LsuV1 with io_req_N_ready reading the
                 queue's count alone, as the snapshot's does: the negative
                 control, which loses requests when the queue fills

Every module other than LsuV1 must be the same text in both surgery
outputs, or this stops: the surgery is meant to touch LsuV1 alone.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

MODULE = re.compile(r"^module\s+(\w+)\s*\(.*?^endmodule\b", re.M | re.S)
INSTANCE = re.compile(r"^\s+(\w+)\s+\w+\s*\(", re.M)


def fail(msg):
    sys.exit("lsu_variants: " + msg)


def surgery(script, snapshot, args):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(
            [sys.executable, "-I", script, "--out-dir", d] + args + [snapshot],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with open(os.path.join(d, os.path.basename(snapshot))) as f:
            return f.read()


def modules(text):
    found = {}
    for m in MODULE.finditer(text):
        if m.group(1) in found:
            fail("module %s defined twice" % m.group(1))
        found[m.group(1)] = m.group(0)
    return found


def closure(mods, top):
    seen = []
    todo = [top]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.append(name)
        todo += [n for n in INSTANCE.findall(mods[name]) if n in mods]
    return seen


def renamed(mods, names, suffix):
    out = []
    for name in names:
        text = mods[name]
        for other in names:
            text = re.sub(r"\b%s\b" % other, other + suffix, text)
        out.append(text)
    return "\n\n".join(out) + "\n"


def negative_control(lsu):
    bad, n = re.subn(r"_ctrl_credit < 5'h", "{1'h0, _ctrl_io_count} < 5'h", lsu)
    if n != 4:
        fail("the negative control found %d credit compares, not 4" % n)
    return bad


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--surgery", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()
    ref = modules(surgery(a.surgery, a.snapshot, []))
    exmem = modules(surgery(a.surgery, a.snapshot, ["--address-register"]))
    if sorted(ref) != sorted(exmem):
        fail("the surgery added or removed modules")
    changed = [n for n in ref if ref[n] != exmem[n]]
    if changed != ["LsuV1"]:
        fail("the surgery changed %s, not LsuV1 alone" % changed)
    names = closure(ref, "LsuV1")
    if closure(exmem, "LsuV1") != names:
        fail("the surgered LsuV1 instantiates other modules")
    bad = dict(exmem)
    bad["LsuV1"] = negative_control(exmem["LsuV1"])
    for suffix, mods in (("_ref", ref), ("_exmem", exmem), ("_bad", bad)):
        with open(os.path.join(a.out_dir, "lsu%s.v" % suffix), "w") as f:
            f.write(renamed(mods, names, suffix))


if __name__ == "__main__":
    main()
