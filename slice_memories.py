#!/usr/bin/env python3
"""AUTO_MEMORIES for one Verilog slice, from ORFS's own memories modules.

ORFS's gen_memories.py detects the memories of the whole design. With
verilog_slices each kept module detects its own, so an edit elsewhere
neither waits on nor changes them:

  regfiles  AUTO_MEMORIES_REGFILES' register files, which depend on their
            specs and not on the Verilog: generated once for every slice.
  slice     the memories of one slice, from extract_memories.tcl's netlist
            JSON of the slice, plus the register files: the memories
            directory synthesis reads, for that slice alone.
  check     each slice's memories against the whole design's: a memory a
            slice names or shapes differently, or one the design has in a
            slice's modules that the slice did not find, fails the build.

Usage:
  slice_memories.py regfiles --scripts-dir D --out-dir O [--regfile-spec S]...
      [--openroad X] [--lef L]... [--macro-place M]... --platform P
  slice_memories.py slice --scripts-dir D --yosys-json J --top M --slice V
      --regfiles-dir R --out-dir O [--memories F]... --platform P
  slice_memories.py check --global-dir G --global-json J --stamp S
      (--slice-dir DIR --slice V)...
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REGFILE_RECORDS = "regfiles.json"
INVENTORY = "memories.json"

MODULE_LINE = re.compile(
    r"^(?:\(\*.*\*\)\s*)?(?:macro)?module\s+(?:(?:static|automatic)\s+)?"
    r"(\\\S+|[A-Za-z_][A-Za-z0-9_$]*)"
)
NAME_LINE = re.compile(r"^// verilog_slice: (\S+) (\S+)$")
LIB_DATE = re.compile(r'^(\s*date\s*:\s*")[^"]*(";)', re.M)


class MemoriesError(Exception):
    pass


def orfs_memories(scripts_dir):
    """ORFS's memories package, from the flow's own scripts."""
    sys.path.insert(0, str(Path(scripts_dir) / "memories"))
    import detect
    import gen_memories
    import idiomatic
    import schema

    return detect, gen_memories, idiomatic, schema


def slice_modules(slice_path):
    """The modules a slice defines, less the stubs of its kept children."""
    defined = []
    named = []
    for line in Path(slice_path).read_text().splitlines():
        m = NAME_LINE.match(line)
        if m:
            named.append(m.group(1))
            continue
        m = MODULE_LINE.match(line)
        if m:
            defined.append(m.group(1).lstrip("\\"))
    stubs = set(named[1:])
    return [d for d in defined if d not in stubs]


def regfiles(args):
    _, gen_memories, _, schema = orfs_memories(args.scripts_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = gen_memories.run_regfiles(
        [Path(s) for s in args.regfile_spec],
        args.openroad,
        [Path(lef) for lef in args.lef],
        out,
        args.macro_place,
    )
    blackboxes = out / "blackboxes.txt"
    if not blackboxes.exists():
        blackboxes.write_text("")
    schema.dump(records, out / REGFILE_RECORDS, args.platform)


def slice_(args):
    detect, gen_memories, idiomatic, schema = orfs_memories(args.scripts_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    regfile_dir = Path(args.regfiles_dir)
    regfile_records = schema.load(regfile_dir / REGFILE_RECORDS)
    listed = {m.name for m in regfile_records}

    found = detect.scan_yosys_json(Path(args.yosys_json), args.top)
    initialized = detect.initialized_modules(Path(args.yosys_json), args.top)
    for name in sorted(listed & initialized):
        raise MemoriesError(
            "{} has a memory with an initial value, which a register file "
            "from generate_ram does not have; remove it from "
            "AUTO_MEMORIES_REGFILES".format(name)
        )
    idiomatic.apply(found)

    present = set(slice_modules(args.slice))
    overrides = []
    for path in args.memories:
        overrides.extend(o for o in schema.load(Path(path)) if o.name in present)
    memories = schema.merge(found, overrides)
    override_names = {o.name for o in overrides}
    for mem in memories:
        mem.kind = "fakeram" if mem.idiomatic else "flops"
        if mem.name in override_names:
            mem.source = "override"

    inventory = out / INVENTORY
    schema.dump(memories, inventory, args.platform)
    converted = [m for m in memories if m.idiomatic]
    for mem in converted:
        schema.validate_emittable(mem)
    if converted:
        subprocess.check_call(
            [
                sys.executable,
                str(gen_memories.FAKERAM_RUN_PY),
                "--orfs_asap7_backend",
                "--output_dir",
                str(out),
                str(inventory),
            ]
        )
    else:
        (out / "blackboxes.txt").write_text("")

    # The generator's own scripts (*.tcl) name the directory they ran in
    # and are no view of a memory; the rest is what the whole design has.
    for f in sorted(regfile_dir.iterdir()):
        if f.name not in ("blackboxes.txt", REGFILE_RECORDS) and f.suffix != ".tcl":
            shutil.copyfile(f, out / f.name)
    with (out / "blackboxes.txt").open("a") as f:
        f.write((regfile_dir / "blackboxes.txt").read_text())
    if regfile_records:
        memories = [m for m in memories if m.name not in listed] + regfile_records
        schema.dump(memories, inventory, args.platform)
    for lib in sorted(out.glob("*.lib")):
        lib.write_text(undated(lib.read_text()))


def undated(text):
    """A Liberty file without the date FakeRAM writes into it, so a slice's
    views change only when its memories do."""
    return LIB_DATE.sub(r"\1\2", text)


def records(path):
    return {m["name"]: m for m in json.loads(Path(path).read_text())["memories"]}


def blackbox_names(path):
    return {
        line.split()[0] for line in Path(path).read_text().splitlines() if line.strip()
    }


def check(args):
    global_dir = Path(args.global_dir)
    design = records(args.global_json)
    design_blackboxes = blackbox_names(global_dir / "blackboxes.txt")
    problems = []
    for slice_dir, slice_path in zip(args.slice_dir, args.slice):
        slice_dir = Path(slice_dir)
        where = Path(slice_path).name
        for name, record in sorted(records(slice_dir / INVENTORY).items()):
            if design.get(name) != record:
                problems.append(
                    "{}: memory {} is not the whole design's: its name or shape "
                    "depends on context outside the slice".format(where, name)
                )
        found = blackbox_names(slice_dir / "blackboxes.txt")
        for name in sorted(found - design_blackboxes):
            problems.append(
                "{}: {} is a black box here and not in the whole design".format(
                    where, name
                )
            )
        for name in sorted(
            (design_blackboxes & set(slice_modules(slice_path))) - found
        ):
            problems.append(
                "{}: the whole design makes a macro of {}, which this slice "
                "defines but did not find as a memory: the memory spans "
                "slices or depends on context outside this one".format(where, name)
            )
        for f in sorted(slice_dir.iterdir()):
            if f.name in ("blackboxes.txt", INVENTORY):
                continue
            other = global_dir / f.name
            same = other.exists() and (
                undated(other.read_text()) == undated(f.read_text())
                if f.suffix == ".lib"
                else other.read_bytes() == f.read_bytes()
            )
            if not same:
                problems.append(
                    "{}: {} differs from the whole design's".format(where, f.name)
                )
    if problems:
        raise MemoriesError("\n".join(problems))
    Path(args.stamp).write_text("")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("regfiles")
    p.add_argument("--scripts-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--regfile-spec", action="append", default=[])
    p.add_argument("--openroad")
    p.add_argument("--lef", action="append", default=[])
    p.add_argument("--macro-place", action="append", default=[])
    p.add_argument("--platform", required=True)

    p = sub.add_parser("slice")
    p.add_argument("--scripts-dir", required=True)
    p.add_argument("--yosys-json", required=True)
    p.add_argument("--top", required=True)
    p.add_argument("--slice", required=True)
    p.add_argument("--regfiles-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--memories", action="append", default=[])
    p.add_argument("--platform", required=True)

    p = sub.add_parser("check")
    p.add_argument("--global-dir", required=True)
    p.add_argument("--global-json", required=True)
    p.add_argument("--stamp", required=True)
    p.add_argument("--slice-dir", action="append", default=[])
    p.add_argument("--slice", action="append", default=[])

    args = parser.parse_args(argv)
    try:
        {"regfiles": regfiles, "slice": slice_, "check": check}[args.command](args)
    except MemoriesError as e:
        print("slice_memories: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
