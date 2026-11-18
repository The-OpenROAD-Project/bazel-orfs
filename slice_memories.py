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
  union     the design's memories, every slice's, the top's included,
            together: the memories directory and memories.json that the
            merge, 1_synth.odb and every later stage read. A memory or view
            two slices disagree on fails the build, naming both.
  check     each slice's memories, and their union, against the whole
            design's: a memory a slice names or shapes differently, one the
            design has in a slice's modules that the slice did not find, or
            a union that is not the whole design's fails the build.

Usage:
  slice_memories.py regfiles --scripts-dir D --out-dir O [--regfile-spec S]...
      [--openroad X] [--lef L]... [--macro-place M]... --platform P
  slice_memories.py slice --scripts-dir D --yosys-json J --top M --slice V
      --regfiles-dir R --out-dir O [--memories F]... --platform P
  slice_memories.py union --out-dir O --json J --regfiles-dir R
      (--slice-dir DIR --slice-name M)...
  slice_memories.py check --global-dir G --global-json J --stamp S
      [--union-dir U --union-json K] (--slice-dir DIR --slice V)...
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
    specs = [Path(s) for s in args.regfile_spec]
    cores = gen_memories.run_regfiles(
        specs,
        args.openroad,
        [Path(lef) for lef in args.lef],
        out,
        args.macro_place,
    )
    gen_memories.write_blackboxes(out, cores)
    records = gen_memories.regfile_memories(specs, args.macro_place)
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

    # A listed register file's record replaces the module's before
    # FakeRAM runs, as in gen_memories.py, so FakeRAM builds no view of it.
    if regfile_records:
        memories = [m for m in memories if m.name not in listed] + regfile_records
    inventory = out / INVENTORY
    schema.dump(memories, inventory, args.platform)
    converted = sorted((m for m in memories if m.idiomatic), key=lambda m: m.name)
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
    gen_memories.write_blackboxes(out, [m.name for m in converted])

    # The generator's own scripts (*.tcl) name the directory they ran in
    # and are no view of a memory; the rest is what the whole design has.
    for f in sorted(regfile_dir.iterdir()):
        if f.name not in ("blackboxes.txt", REGFILE_RECORDS) and f.suffix != ".tcl":
            shutil.copyfile(f, out / f.name)
    with (out / "blackboxes.txt").open("a") as f:
        f.write((regfile_dir / "blackboxes.txt").read_text())
    for lib in sorted(out.glob("*.lib")):
        lib.write_text(undated(lib.read_text()))


def undated(text):
    """A Liberty file without the date FakeRAM writes into it, so a slice's
    views change only when its memories do."""
    return LIB_DATE.sub(r"\1\2", text)


def records(path):
    return {m["name"]: m for m in json.loads(Path(path).read_text())["memories"]}


def blackbox_lines(path):
    return [line for line in Path(path).read_text().splitlines() if line.strip()]


def union(args):
    """The slices' memories as gen_memories.py writes the whole design's:
    memories.json sorted by name, blackboxes.txt with FakeRAM's macros
    sorted by name and the register files' after them, every view once."""
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    header = None
    memories = {}
    blackboxes = {}
    views = {}

    def once(seen, key, name, value, what):
        first, value_first = seen.setdefault(key, (name, value))
        if value_first != value:
            raise MemoriesError(
                "{} {} is not the same in {} and {}".format(what, key, first, name)
            )

    for slice_dir, name in zip(args.slice_dir, args.slice_name):
        slice_dir = Path(slice_dir)
        doc = json.loads((slice_dir / INVENTORY).read_text())
        this = {k: v for k, v in doc.items() if k != "memories"}
        if header is None:
            header = (name, this)
        elif header[1] != this:
            raise MemoriesError(
                "{} and {} write memories.json for a different platform or "
                "version".format(header[0], name)
            )
        for record in doc["memories"]:
            once(memories, record["name"], name, record, "memory")
        for line in blackbox_lines(slice_dir / "blackboxes.txt"):
            once(blackboxes, line.split()[0], name, line, "black box")
        for f in sorted(slice_dir.iterdir()):
            if f.name not in ("blackboxes.txt", INVENTORY):
                once(views, f.name, name, f.read_bytes(), "view")

    doc = dict(header[1]) if header else {}
    doc["memories"] = [memories[m][1] for m in sorted(memories)]
    Path(args.json).write_text(json.dumps(doc, indent=2) + "\n")
    regfile_lines = blackbox_lines(Path(args.regfiles_dir) / "blackboxes.txt")
    regfile_macros = {line.split()[0] for line in regfile_lines}
    (out / "blackboxes.txt").write_text(
        "".join(
            blackboxes[m][1] + "\n"
            for m in sorted(blackboxes)
            if m not in regfile_macros
        )
        + "".join(line + "\n" for line in regfile_lines)
    )
    for name in sorted(views):
        (out / name).write_bytes(views[name][1])


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
    if args.union_dir:
        problems.extend(union_problems(global_dir, args.global_json, args))
    if problems:
        raise MemoriesError("\n".join(problems))
    Path(args.stamp).write_text("")


def union_problems(global_dir, global_json, args):
    """What sets the slices' union apart from the whole design's memories.
    The whole design's FakeRAM views are dated and the union's are not;
    its register files' generator scripts (*.tcl) are no view."""
    union_dir = Path(args.union_dir)
    problems = []
    if Path(global_json).read_bytes() != Path(args.union_json).read_bytes():
        problems.append("the slices' memories.json is not the whole design's")
    design_views = {f.name for f in global_dir.iterdir() if f.suffix != ".tcl"}
    union_views = {f.name for f in union_dir.iterdir()}
    for name in sorted(design_views - union_views):
        problems.append("the slices have no {}, the whole design has".format(name))
    for name in sorted(union_views - design_views):
        problems.append("the slices have {}, the whole design has not".format(name))
    for name in sorted(design_views & union_views):
        ours = (union_dir / name).read_bytes()
        theirs = (global_dir / name).read_bytes()
        if name.endswith(".lib"):
            ours = undated(ours.decode()).encode()
            theirs = undated(theirs.decode()).encode()
        if ours != theirs:
            problems.append("the slices' {} is not the whole design's".format(name))
    return problems


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

    p = sub.add_parser("union")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--json", required=True)
    p.add_argument("--regfiles-dir", required=True)
    p.add_argument("--slice-dir", action="append", default=[])
    p.add_argument("--slice-name", action="append", default=[])

    p = sub.add_parser("check")
    p.add_argument("--union-dir")
    p.add_argument("--union-json")
    p.add_argument("--global-dir", required=True)
    p.add_argument("--global-json", required=True)
    p.add_argument("--stamp", required=True)
    p.add_argument("--slice-dir", action="append", default=[])
    p.add_argument("--slice", action="append", default=[])

    args = parser.parse_args(argv)
    try:
        {
            "regfiles": regfiles,
            "slice": slice_,
            "union": union,
            "check": check,
        }[
            args.command
        ](args)
    except MemoriesError as e:
        print("slice_memories: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
