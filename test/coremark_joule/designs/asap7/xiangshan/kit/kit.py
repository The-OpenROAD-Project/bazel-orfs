#!/usr/bin/env python3
"""Assemble the XSTile implementation kit.

  kit.py sdc --design <constraints.sdc> --platform <platform constraints.sdc> --out <XSTile.sdc>
      the design's SDC with the platform part it sources inlined, so that
      it reads without an ORFS environment
  kit.py tar --out <kit.tar.gz> --manifest <kit_manifest.txt> --netlist <1_2_yosys.v>
      --sdc <XSTile.sdc> --itf <asap7.itf> --sta <sta.tcl>
      --memories-lef <lef> --memories-lib <lib>
      [--regfile <module>=<file>,<file>...]... [--file <kit path>=<file>]...
      -- <platform file>...
      the kit as a deterministic .tar.gz: the platform files the manifest
      names (kit_manifest.tcl), liberty decompressed, under the layout
      README.pdf describes
  kit.py add --in <kit.tar.gz> --out <kit.tar.gz> <kit path>=<file>...
      the same archive with more files
  kit.py unpack --in <kit.tar.gz> --dir <dir>
  kit.py pin --status <stable-status.txt> --netlist <XSTile.v> --out <pin.json>
      the SHA-256 of the netlist a pin of the kit's facts describes, and
      the day
  kit.py pick --manifest <kit_manifest.txt> --kind <kind> -- <platform file>...
      the one platform file of that kind the manifest names

The archive's files sit under xiangshan-xstile-asap7/. Python 3.6.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile

ROOT = "xiangshan-xstile-asap7"
SOURCE_LINE = re.compile(
    r"^(\s*)source\s+\$::env\(PLATFORM_DIR\)/constraints\.sdc\s*$", re.M
)


def inline_sdc(design, platform):
    found = SOURCE_LINE.findall(design)
    if len(found) != 1:
        raise SystemExit(
            "kit: the design SDC sources the platform constraints %d times, expected once"
            % len(found)
        )
    indent = found[0]
    body = "\n".join(
        (indent + line) if line.strip() else ""
        for line in platform.rstrip("\n").split("\n")
    )
    marker = "%s# inlined from the platform's constraints.sdc\n" % indent
    return SOURCE_LINE.sub(lambda m: marker + body, design)


def read_manifest(path):
    entries = []
    for line in open(path):
        line = line.strip()
        if line:
            kind, rel = line.split(" ", 1)
            entries.append((kind, rel))
    return entries


def resolve(entries, platform_files):
    """Each manifest path to the platform file it names: the file whose
    path ends in /<platform name>/<relative path>."""
    out = []
    for kind, rel in entries:
        hits = [p for p in platform_files if p.endswith("/" + rel)]
        if len(hits) != 1:
            raise SystemExit(
                "kit: %s %s matches %d platform files" % (kind, rel, len(hits))
            )
        out.append((kind, rel, hits[0]))
    return out


class Archive(object):
    """A .tar.gz whose bytes depend only on its members' names and bytes."""

    def __init__(self, path):
        self.raw = open(path, "wb")
        self.gz = gzip.GzipFile(filename="", mode="wb", fileobj=self.raw, mtime=0)
        self.tar = tarfile.open(fileobj=self.gz, mode="w", format=tarfile.PAX_FORMAT)
        self.names = set()

    def add_bytes(self, name, data):
        if name in self.names:
            raise SystemExit("kit: %s twice in the kit" % name)
        self.names.add(name)
        info = tarfile.TarInfo("%s/%s" % (ROOT, name))
        info.size = len(data)
        info.mode = 0o644
        info.mtime = 0
        self.tar.addfile(info, io.BytesIO(data))

    def add_dir(self, name):
        info = tarfile.TarInfo("%s/%s" % (ROOT, name))
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        info.mtime = 0
        self.tar.addfile(info)

    def add_file(self, name, path):
        with open(path, "rb") as f:
            data = f.read()
        if path.endswith(".gz"):
            data = gzip.decompress(data)
            name = name[: -len(".gz")] if name.endswith(".gz") else name
        self.add_bytes(name, data)

    def close(self):
        self.tar.close()
        self.gz.close()
        self.raw.close()


def cmd_sdc(a):
    with open(a.design) as f:
        design = f.read()
    with open(a.platform) as f:
        platform = f.read()
    with open(a.out, "w") as f:
        f.write(inline_sdc(design, platform))


def pairs(values):
    out = []
    for v in values:
        k, _, rest = v.partition("=")
        if not rest:
            raise SystemExit("kit: %s is not <name>=<file>" % v)
        out.append((k, rest))
    return out


def cmd_tar(a):
    entries = resolve(read_manifest(a.manifest), a.platform_files)
    kinds = {k for k, _, _ in entries}
    for need in ("tech_lef", "cell_lef", "cell_lib"):
        if need not in kinds:
            raise SystemExit("kit: the manifest names no %s" % need)
    ar = Archive(a.out)
    for kind, rel, path in sorted(entries, key=lambda e: e[1]):
        base = os.path.basename(rel)
        if kind == "tech_lef":
            ar.add_file("tech/asap7_tech.lef", path)
        elif kind == "cell_lef":
            ar.add_file("cells/lef/" + base, path)
        elif kind == "cell_lib":
            ar.add_file("cells/lib/" + base, path)
    ar.add_file("netlist/XSTile.v", a.netlist)
    ar.add_file("constraints/XSTile.sdc", a.sdc)
    ar.add_file("tech/asap7.itf", a.itf)
    ar.add_file("check/sta.tcl", a.sta)
    ar.add_file("macros/lef/memories.lef", a.memories_lef)
    ar.add_file("macros/lib/memories.lib", a.memories_lib)
    for module, files in sorted(pairs(a.regfile)):
        files = files.split(",")
        lefs = [f for f in files if f.endswith(".lef")]
        libs = [f for f in files if f.endswith(".lib")]
        nets = [f for f in files if f.endswith("1_2_yosys.v")]
        if len(lefs) != 1 or len(libs) != 1 or len(nets) != 1:
            raise SystemExit(
                "kit: register file %s: want one .lef, one .lib and one 1_2_yosys.v, got %s"
                % (module, files)
            )
        ar.add_file("macros/lef/%s.lef" % module, lefs[0])
        ar.add_file("macros/lib/%s.lib" % module, libs[0])
        ar.add_file("macros/verilog/%s.v" % module, nets[0])
    for name, path in sorted(pairs(a.file)):
        ar.add_file(name, path)
    ar.add_dir("results")
    ar.close()


def cmd_add(a):
    src = tarfile.open(a.input, "r:gz")
    ar = Archive(a.out)
    for m in src.getmembers():
        name = m.name[len(ROOT) + 1 :]
        if m.isdir():
            ar.add_dir(name)
        else:
            ar.add_bytes(name, src.extractfile(m).read())
    for name, path in sorted(pairs(a.files)):
        ar.add_file(name, path)
    ar.close()


def cmd_unpack(a):
    with tarfile.open(a.input, "r:gz") as t:
        for m in t.getmembers():
            if (
                m.name != ROOT
                and not m.name.startswith(ROOT + "/")
                or ".." in m.name.split("/")
            ):
                raise SystemExit("kit: %s is outside %s/" % (m.name, ROOT))
        t.extractall(a.dir)


def stable_status(path):
    values = {}
    with open(path) as f:
        for line in f:
            k, _, v = line.rstrip("\n").partition(" ")
            values[k] = v
    return values


def cmd_pin(a):
    """The netlist the facts describe, by content, and the day: a commit
    would name a branch the merge rebases away."""
    digest = hashlib.sha256()
    with open(a.netlist, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    pin = {
        "date": stable_status(a.status).get("STABLE_BUILD_DATE", "unstamped"),
        "netlist_sha256": digest.hexdigest(),
    }
    with open(a.out, "w") as f:
        json.dump(pin, f, indent=2, sort_keys=True)
        f.write("\n")


def cmd_pick(a):
    hits = [
        path
        for kind, _, path in resolve(read_manifest(a.manifest), a.platform_files)
        if kind == a.kind
    ]
    if len(hits) != 1:
        raise SystemExit(
            "kit: the manifest names %d files of kind %s, expected one"
            % (len(hits), a.kind)
        )
    print(hits[0])


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("sdc")
    s.add_argument("--design", required=True)
    s.add_argument("--platform", required=True)
    s.add_argument("--out", required=True)
    t = sub.add_parser("tar")
    for flag in (
        "out",
        "manifest",
        "netlist",
        "sdc",
        "itf",
        "sta",
        "memories-lef",
        "memories-lib",
    ):
        t.add_argument("--" + flag, required=True)
    t.add_argument("--regfile", action="append", default=[])
    t.add_argument("--file", action="append", default=[])
    t.add_argument("platform_files", nargs="*")
    d = sub.add_parser("add")
    d.add_argument("--in", dest="input", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("files", nargs="+")
    u = sub.add_parser("unpack")
    u.add_argument("--in", dest="input", required=True)
    u.add_argument("--dir", required=True)
    k = sub.add_parser("pick")
    k.add_argument("--manifest", required=True)
    k.add_argument("--kind", required=True)
    k.add_argument("platform_files", nargs="*")
    n = sub.add_parser("pin")
    n.add_argument("--status", required=True)
    n.add_argument("--netlist", required=True)
    n.add_argument("--out", required=True)
    a = p.parse_args(argv)
    {
        "pin": cmd_pin,
        "sdc": cmd_sdc,
        "tar": cmd_tar,
        "add": cmd_add,
        "unpack": cmd_unpack,
        "pick": cmd_pick,
    }.get(a.cmd, lambda _: p.error("a command"))(a)


if __name__ == "__main__":
    main()
