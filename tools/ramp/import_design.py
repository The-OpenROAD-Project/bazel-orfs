"""`bazelisk run //:import -- <ORFS design dir>`: an ORFS design into this clone.

The on-ramp. Reads an ORFS design's config.mk, copies every file it names
into imported/<platform>/<design>/ of this workspace and writes a
BUILD.bazel with one orfs_flow() that builds it. The ORFS checkout is only
read: delete the clone and nothing of it is left behind.

What config.mk says is asked of ORFS's own make (`make print-VAR`), not
re-implemented: wildcards, includes, conditionals and platform defaults
come out the way the ORFS flow would see them. The variables imported are
the ones the design's own makefiles assign, and whose value differs from
what the platform alone gives.

Anything import cannot map is refused, naming it and this file, rather
than guessed: a project with its own ORFS changes is expected to have an
AI patch this file to match. Not handled yet, and refused: BLOCKS
(hierarchical macros).

    bazelisk run //:import -- ~/OpenROAD-flow-scripts/flow/designs/asap7/gcd
    bazelisk run //:import -- <design dir> --orfs <ORFS flow dir> --dest <dir>
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

MARKER = "# Imported by `bazelisk run //:import`"

# Set by orfs_flow() from its own attributes, or the flow's own business.
STRUCTURAL = {"PLATFORM", "DESIGN_NAME", "DESIGN_NICKNAME", "VERILOG_FILES"}

# Variables a design may name as directories, and how they reach Bazel.
DIRECTORY_VARS = {"VERILOG_INCLUDE_DIRS"}

# Makefile variables ORFS's own machinery sets, never a design setting.
MAKE_INTERNAL = {"MAKEFILE_LIST", "CURDIR", "SHELL", "MAKEFLAGS", "MAKE"}

ASSIGN = re.compile(
    r"^\s*(?:export\s+|override\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\?|:|::|\+|!)?="
)


class Refused(Exception):
    """A design import cannot map; the message names it and what to do."""


def refuse(msg):
    raise Refused(
        msg + "\n(tools/ramp/import_design.py is the file to patch; docs/ramps.md)"
    )


def make_print(make, flow, config, names):
    """{name: value} for each variable, as ORFS's make sees it."""
    cmd = [make, "--no-print-directory", "-C", flow, "DESIGN_CONFIG=" + config]
    cmd += ["print-" + n for n in names]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        refuse(
            "ORFS's make could not read {}:\n{}".format(
                config, r.stderr.strip()[-2000:]
            )
        )
    values = {}
    for line in r.stdout.splitlines():
        name, sep, value = line.partition(": ")
        if sep and name in names:
            values[name] = value.strip()
        elif line.endswith(":") and line[:-1] in names:
            values[line[:-1]] = ""
    missing = [n for n in names if n not in values]
    if missing:
        refuse("make printed no value for {}".format(", ".join(missing)))
    return values


def design_makefiles(flow, makefile_list):
    """The makefiles ORFS read that belong to the design, not to ORFS."""
    own = []
    for f in makefile_list.split():
        p = os.path.normpath(os.path.join(flow, f))
        rel = os.path.relpath(p, flow)
        if rel == "Makefile" or rel.startswith(("scripts/", "util/", "platforms/")):
            continue
        own.append(p)
    return own


def assigned_names(makefiles):
    names = []
    for f in makefiles:
        text = open(f).read().replace("\\\n", " ")
        for line in text.splitlines():
            m = ASSIGN.match(line)
            if m and m.group(1) not in names and m.group(1) not in MAKE_INTERNAL:
                names.append(m.group(1))
    return names


def is_bazel_orfs(ws):
    try:
        with open(os.path.join(ws, "MODULE.bazel")) as f:
            return re.search(r'module\(\s*name\s*=\s*"bazel-orfs"', f.read())
    except OSError:
        return False


def find_flow(design_dir):
    """The ORFS flow/ directory above a design directory."""
    d = os.path.abspath(design_dir)
    while d != os.path.dirname(d):
        if os.path.isfile(os.path.join(d, "scripts", "variables.mk")):
            return d
        if os.path.isfile(os.path.join(d, "flow", "scripts", "variables.mk")):
            return os.path.join(d, "flow")
        d = os.path.dirname(d)
    refuse(
        "no ORFS flow/ directory above {}: pass --orfs <ORFS flow dir>".format(
            design_dir
        )
    )


def tokens(flow, value):
    """A value's words, a shell glob expanded as the recipe's shell would."""
    out = []
    for t in value.split():
        if looks_like_path(t) and any(c in t for c in "*?["):
            hits = sorted(glob.glob(t if os.path.isabs(t) else os.path.join(flow, t)))
            if not hits:
                refuse("{} matches no file".format(t))
            out += hits
        else:
            out.append(t)
    return out


def flow_variables(flow):
    """The variables ORFS's flow reads, from its scripts/variables.yaml."""
    names = set()
    with open(os.path.join(flow, "scripts", "variables.yaml")) as f:
        for line in f:
            m = re.match(r"^([A-Z][A-Z0-9_]*):", line)
            if m:
                names.add(m.group(1))
    return names


def resolve(flow, token):
    """A token's path, if it names a file or directory, else None."""
    p = token if os.path.isabs(token) else os.path.join(flow, token)
    return os.path.normpath(p) if os.path.exists(p) else None


def looks_like_path(token):
    return "/" in token and not token.startswith("-")


class Vendor:
    """Copies files into the package, each under a path that says where from."""

    def __init__(self, flow, design_dir, dest):
        self.flow = flow
        self.design_dir = design_dir
        self.dest = dest
        self.copied = {}  # source path -> package-relative path

    def place(self, src):
        if src in self.copied:
            return self.copied[src]
        if src == self.design_dir or src.startswith(self.design_dir + os.sep):
            rel = os.path.relpath(src, self.design_dir)
        elif src.startswith(self.flow + os.sep):
            rel = os.path.relpath(src, self.flow)
        else:
            rel = os.path.join("outside", os.path.basename(src))
        if rel in self.copied.values():
            refuse("two inputs would be copied to {}: {}".format(rel, src))
        to = os.path.join(self.dest, rel)
        os.makedirs(os.path.dirname(to), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, to, dirs_exist_ok=True)
        else:
            shutil.copy2(src, to)
        self.copied[src] = rel
        return rel


def starlark(value, indent=4):
    """A Python dict/list/str as Starlark, the way buildifier writes it."""
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            "{}    {}: {},".format(pad, starlark(k), starlark(v, indent + 4))
            for k, v in sorted(value.items())
        ]
        return "{\n" + "\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list):
        if len(value) == 1:
            return "[" + starlark(value[0]) + "]"
        items = ["{}    {},".format(pad, starlark(v)) for v in value]
        return "[\n" + "\n".join(items) + "\n" + pad + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def import_design(make, flow, design_dir, dest, pkg):
    config = os.path.join(design_dir, "config.mk")
    if not os.path.isfile(config):
        refuse("no config.mk in {}".format(design_dir))

    first = make_print(make, flow, config, ["MAKEFILE_LIST", "PLATFORM"])
    platform = first["PLATFORM"]
    if not platform:
        refuse("{} sets no PLATFORM".format(config))
    makefiles = design_makefiles(flow, first["MAKEFILE_LIST"])
    names = assigned_names(makefiles)
    if "BLOCKS" in names:
        refuse(
            "{} sets BLOCKS (hierarchical macros), which import does not handle"
            " yet: each block is an orfs_flow() of its own, passed to the parent"
            " as macros = [...]".format(config)
        )
    wanted = sorted(set(names) | {"DESIGN_NAME", "DESIGN_NICKNAME", "VERILOG_FILES"})
    values = make_print(make, flow, config, wanted)

    # The platform alone: a variable whose value it already gives is not
    # the design's setting, whatever branch of a conditional assigned it.
    stub = os.path.join(dest, ".platform_only.mk")
    os.makedirs(dest, exist_ok=True)
    with open(stub, "w") as f:
        f.write("export PLATFORM = {}\n".format(platform))
        f.write("export DESIGN_NAME = {}\n".format(values["DESIGN_NAME"]))
        f.write("export DESIGN_NICKNAME = {}\n".format(values["DESIGN_NICKNAME"]))
    baseline = make_print(make, flow, stub, wanted)
    os.remove(stub)

    vendor = Vendor(flow, os.path.abspath(design_dir), dest)
    vendor.place(config)

    verilog = []
    for t in tokens(flow, values["VERILOG_FILES"]):
        p = resolve(flow, t)
        if not p or os.path.isdir(p):
            refuse("VERILOG_FILES names {}, which is not a file".format(t))
        verilog.append(vendor.place(p))
    if not verilog:
        refuse("VERILOG_FILES is empty in {}".format(config))

    known = flow_variables(flow)
    sources, arguments, stage_data, helpers = {}, {}, [], []
    for name in wanted:
        if name in STRUCTURAL:
            continue
        value = values[name]
        if value == baseline[name]:
            continue
        toks = tokens(flow, value)
        paths = [resolve(flow, t) for t in toks]
        if toks and all(paths):
            if name in DIRECTORY_VARS:
                rels = [vendor.place(p) for p in paths]
                arguments[name] = " ".join(os.path.join(pkg, r) for r in rels)
                stage_data += [r + "/**" for r in rels]
                continue
            dirs = [t for t, p in zip(toks, paths) if os.path.isdir(p)]
            if dirs and name not in known:
                # A design's own helper (SRC_HOME): the flow never reads
                # it, and the variables built from it are expanded already.
                helpers.append(name)
                continue
            if dirs:
                refuse(
                    "{} names directories ({}): only {} may".format(
                        name, " ".join(dirs), ", ".join(sorted(DIRECTORY_VARS))
                    )
                )
            sources[name] = [vendor.place(p) for p in paths]
            continue
        broken = [t for t, p in zip(toks, paths) if not p and looks_like_path(t)]
        if broken:
            refuse("{} names {}, which does not exist".format(name, " ".join(broken)))
        arguments[name] = value

    if helpers:
        print(
            "import: left out {}, directories the flow does not read".format(
                ", ".join(helpers)
            )
        )
    # A variable ORFS's flow does not know is the project's own, read by
    # its own scripts: orfs_flow() takes those as user_*, unvalidated.
    split = {}
    for kind, d in (("arguments", arguments), ("sources", sources)):
        split[kind] = {k: v for k, v in d.items() if k in known}
        split["user_" + kind] = {k: v for k, v in d.items() if k not in known}
    write_build(
        dest,
        values,
        platform,
        verilog,
        split,
        stage_data,
        os.path.relpath(config, flow),
    )
    return values["DESIGN_NICKNAME"] or values["DESIGN_NAME"], vendor.copied


def write_build(dest, values, platform, verilog, split, stage_data, origin):
    name = values["DESIGN_NICKNAME"] or values["DESIGN_NAME"]
    frontend = ""
    arguments = split["arguments"]
    if "SYNTH_HDL_FRONTEND" not in arguments and arguments.get("SYNTH_USE_SYN") != "1":
        frontend = (
            "#\n# ORFS's make reads the Verilog with yosys's own frontend unless\n"
            "# SYNTH_HDL_FRONTEND says otherwise; orfs_flow() synthesises with\n"
            '# slang (docs/agent-rules.md, "Synthesis frontend").\n'
        )
    lines = [
        MARKER + " from an ORFS design:",
        "#   {}, kept here as config.mk".format(origin),
        "# Written literally, one setting per config.mk variable; ask your AI",
        "# to make it idiomatic. Re-running import replaces this package.",
    ]
    if frontend:
        lines += frontend.rstrip("\n").split("\n")
    lines += [
        'load("//:openroad.bzl", "orfs_flow")',
        "",
        "orfs_flow(",
        "    name = {},".format(starlark(name)),
    ]
    if values["DESIGN_NAME"] != name:
        lines.append("    top = {},".format(starlark(values["DESIGN_NAME"])))
    if arguments:
        lines.append("    arguments = {},".format(starlark(arguments)))
    lines.append("    pdk = {},".format(starlark("@orfs//flow:" + platform)))
    if split["sources"]:
        lines.append("    sources = {},".format(starlark(split["sources"])))
    if stage_data:
        lines += [
            "    stage_data = {",
            '        "synth": glob({}),'.format(starlark(stage_data, 8)),
            "    },",
        ]
    for kind in ("user_arguments", "user_sources"):
        if split[kind]:
            lines.append(
                "    # Not ORFS variables: the project's own, read by its scripts."
            )
            lines.append("    {} = {},".format(kind, starlark(split[kind])))
    lines.append("    verilog_files = {},".format(starlark(verilog)))
    lines.append(")")
    with open(os.path.join(dest, "BUILD.bazel"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design_dir", help="an ORFS design directory, with its config.mk")
    ap.add_argument("--orfs", help="the ORFS flow/ directory; found above design_dir")
    ap.add_argument("--dest", help="default imported/<platform>/<design>")
    ap.add_argument("--make", default=os.environ.get("IMPORT_MAKE", "make"))
    args = ap.parse_args(argv)

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    cwd = os.environ.get("BUILD_WORKING_DIRECTORY", ws)
    design_dir = os.path.abspath(os.path.join(cwd, args.design_dir))
    if os.path.basename(design_dir) == "config.mk":
        design_dir = os.path.dirname(design_dir)
    make = args.make
    if os.sep in make:
        make = os.path.abspath(make)
    try:
        if not is_bazel_orfs(ws):
            refuse(
                "{} is not a bazel-orfs clone: import writes into one, whose"
                " //:openroad.bzl the BUILD.bazel it writes loads".format(ws)
            )
        flow = (
            os.path.abspath(os.path.join(cwd, args.orfs))
            if args.orfs
            else find_flow(design_dir)
        )
        if args.dest:
            dest = os.path.abspath(os.path.join(cwd, args.dest))
        else:
            platform = make_print(
                make,
                flow,
                os.path.join(design_dir, "config.mk"),
                ["PLATFORM", "DESIGN_NICKNAME"],
            )
            dest = os.path.join(
                ws, "imported", platform["PLATFORM"], platform["DESIGN_NICKNAME"]
            )
        if os.path.relpath(dest, ws).startswith(".."):
            refuse("--dest {} is outside this workspace {}".format(dest, ws))
        build = os.path.join(dest, "BUILD.bazel")
        if os.path.exists(dest) and os.listdir(dest):
            if not (os.path.isfile(build) and open(build).read().startswith(MARKER)):
                refuse(
                    "{} exists and is not an import: refusing to replace it".format(
                        dest
                    )
                )
            shutil.rmtree(dest)
        pkg = os.path.relpath(dest, ws)
        name, copied = import_design(make, flow, design_dir, dest, pkg)
    except Refused as e:
        print("import: " + str(e), file=sys.stderr)
        return 1
    print("import: {} files into {}".format(len(copied), os.path.relpath(dest, cwd)))
    for src, rel in sorted(copied.items(), key=lambda kv: kv[1]):
        if rel.startswith("outside/"):
            print("  {} from outside ORFS: {}".format(rel, src))
    print("next:  bazelisk build //{}:{}_synth".format(pkg, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
