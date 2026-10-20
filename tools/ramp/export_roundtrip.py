"""`bazelisk run //tools/ramp:export_roundtrip -- <orfs_flow target>`: export, make, compare.

The check docs/ramps.md asks of an export, for a flow with BLOCKS and a
macro placement snapshot: export it with --snapshot-macro-placement, make
it with ORFS's make up to the parent's floorplan (which builds every block
to finish, as ORFS's BLOCKS does), and compare, flow by flow, ORFS's
2_floorplan.odb with Bazel's on what the macro placement decides
(roundtrip_compare.tcl). Then the negative control: the same comparison
with one macro moved one site must fail, and name the macro. Last, every
literal value in each exported config.mk must be what ORFS's make sees
(`make print-VAR`): a platform or a default that overrides it is a
difference.

ORFS, make and the tools are the ones Bazel used: a dirty-lane tree
(docs/dirty-lane.md) of the flow's synthesis stage carries the pinned ORFS
with its carried patches, and the openroad and yosys the stages ran.

Not a bazel test: it runs bazelisk, and ORFS's make builds every block
to finish. Half an hour for //test/regfile/macro:wide_top_hard, seconds
for //test:lb_32x128_top --abstracts; for XiangShan, see the measured
times in its README before starting one.

    bazelisk run //tools/ramp:export_roundtrip -- //test/regfile/macro:wide_top_hard
    bazelisk run //tools/ramp:export_roundtrip -- --abstracts //test:lb_32x128_top
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

import export_design
from export_design import STAGE_ODB, Refused, bazelisk, build, group_files, refuse

HERE = os.path.dirname(os.path.abspath(__file__))
COMPARE_TCL = os.path.join(HERE, "roundtrip_compare.tcl")
LITERAL = re.compile(r"^[^$]*$")


def read_exports(path):
    """{variable: value} of an exported config.mk."""
    out = {}
    with open(path) as f:
        for line in f:
            m = re.match(
                r"^export ([A-Za-z_][A-Za-z0-9_]*) \??= (.*)$", line.rstrip("\n")
            )
            if m:
                out[m.group(1)] = m.group(2)
    return out


def configs(dest):
    """(rel, config.mk) of the export's top and every block, top first."""
    found = []
    for root, dirs, files in os.walk(dest):
        dirs[:] = sorted(d for d in dirs if d != "inputs")
        if "config.mk" in files:
            found.append((os.path.relpath(root, dest), os.path.join(root, "config.mk")))
    return found


def make_env():
    """This process's environment without its python launcher's settings.

    A py_binary's launcher sets PYTHONSAFEPATH and RUNFILES_*: inherited
    by make, the first stops FakeRAM's run.py importing its own modules.
    """
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "RUNFILES"))
    }
    # the tree is the synthesis stage's; the export's config.mk says every
    # stage's variables, so any stage runs, with none of the tree's own
    env["ORFS_DEPLOY_ANY_STAGE"] = "1"
    env["ORFS_DEPLOY_LATER_VARS"] = "0"
    return env


def compare(openroad, a, b, move="", seeds=True):
    """(same, report lines) of roundtrip_compare.tcl on two .odb files.

    seeds False: standard cells merely PLACED are left out, the seeds
    rtl_macro_placer leaves in a floorplan, which a snapshot skips.
    """
    r = subprocess.run(
        [openroad, "-no_init", "-no_splash", "-exit", COMPARE_TCL],
        env=dict(
            os.environ,
            COMPARE_A=a,
            COMPARE_B=b,
            COMPARE_MOVE=move,
            COMPARE_SEEDS="1" if seeds else "0",
        ),
        capture_output=True,
        text=True,
    )
    lines = [l for l in r.stdout.splitlines() if l.startswith("roundtrip:")]
    if r.returncode or not lines:
        refuse(
            "roundtrip_compare.tcl failed:\n{}".format((r.stdout + r.stderr)[-2000:])
        )
    return lines[-1] == "roundtrip: same", lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("flow", help="an orfs_flow() label, //pkg:name")
    ap.add_argument(
        "--dir",
        default="tmp/export_roundtrip",
        help="where the export, the tools and make's results go",
    )
    ap.add_argument(
        "--drop", action="append", default=[], help="passed to export --drop"
    )
    ap.add_argument(
        "--abstracts", action="store_true", help="passed to export --abstracts"
    )
    ap.add_argument(
        "--start",
        help="passed to export --start: make runs that stage alone, on the"
        " results Bazel built, and its .odb is compared",
    )
    ap.add_argument(
        "--make-arg",
        action="append",
        default=[],
        metavar="VAR=VALUE",
        help="passed to make, e.g. SYNTH_NETLIST_FILES= to synthesise from the RTL",
    )
    args = ap.parse_args(argv)

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    cwd = os.environ.get("BUILD_WORKING_DIRECTORY", ws)
    top = os.path.abspath(os.path.join(cwd, args.dir))
    name = args.flow.rsplit(":", 1)[-1]
    dest = os.path.join(top, name)
    tools = os.path.join(top, "tools")
    work = os.path.join(top, "work")
    try:
        rc = export_design.main(
            ["--snapshot-macro-placement"]
            + ["--drop=" + d for d in args.drop]
            + (["--abstracts"] if args.abstracts else [])
            + (["--start=" + args.start] if args.start else [])
            + [dest, args.flow]
        )
        if rc:
            return rc
        print("roundtrip: the tools, a dirty-lane tree of {}_synth".format(name))
        r = subprocess.run(
            ["bazelisk", "run", "//:dirty", "--", "start", args.flow, "synth"]
            + ["--dir", tools, "--fresh"],
            cwd=ws,
            capture_output=True,
            text=True,
        )
        if r.returncode:
            refuse("//:dirty start failed:\n{}".format(r.stderr[-2000:]))
        with open(os.path.join(tools, "make.stage")) as f:
            runner = re.search(r"^exec (\S+)", f.read(), re.M).group(1)
        main_dir = os.path.join(tools, "_main")
        openroad = os.path.join(tools, "openroad+", "openroad")

        found = configs(dest)
        exports = {rel: read_exports(path) for rel, path in found}
        platform = exports["."]["PLATFORM"]
        nickname = exports["."].get("DESIGN_NICKNAME") or exports["."]["DESIGN_NAME"]
        stage = args.start or "floorplan"
        odb_name = STAGE_ODB[stage] + ".odb"
        if os.path.exists(work):
            shutil.rmtree(work)
        if args.start:
            # what export shipped: the earlier stages' results, as ORFS's tree
            shutil.copytree(os.path.join(dest, "start", stage), work, symlinks=True)
            target = "do-" + stage
            found = found[:1]
            what = "{} alone, on Bazel's earlier results".format(stage)
        else:
            os.makedirs(work)
            target = os.path.join(work, "results", platform, nickname, "base", odb_name)
            what = "the blocks to finish and the parent to floorplan"
        log = os.path.join(top, "make.log")
        print("roundtrip: make, {}; log in {}".format(what, log))
        start = time.time()
        with open(log, "w") as f:
            r = subprocess.run(
                [runner, "DESIGN_CONFIG=" + found[0][1], "WORK_HOME=" + work]
                + args.make_arg
                + [target],
                cwd=main_dir,
                env=make_env(),
                stdout=f,
                stderr=subprocess.STDOUT,
            )
        minutes = (time.time() - start) / 60
        if r.returncode:
            refuse("make failed after {:.1f} min: see {}".format(minutes, log))
        print("roundtrip: make took {:.1f} min".format(minutes))

        failures = 0
        bazel_odbs = {}
        for rel, path in found:
            e = exports[rel]
            label = open(path).readline().split(" from ")[-1].rstrip(".\n")
            build(ws, odb_name, [label + "_" + stage])
            odb = [
                f
                for f in group_files(ws, label + "_" + stage, odb_name)
                if f.endswith(".odb")
            ]
            execroot = bazelisk(ws, "info", "execution_root").stdout.strip()
            bazel_odbs[rel] = os.path.join(execroot, odb[0])
            nick = e.get("DESIGN_NICKNAME") or e["DESIGN_NAME"]
            made = os.path.join(work, "results", platform, nick, "base", odb_name)
            if "SYNTH_NETLIST_FILES" in e and not args.start:
                # with a netlist, ORFS's synthesis copies it and exits
                # before it reads the RTL, so writes no canonical RTLIL
                cleared = "SYNTH_NETLIST_FILES=" in args.make_arg
                rtlil = os.path.exists(
                    os.path.join(os.path.dirname(made), "1_1_yosys_canonicalize.rtlil")
                )
                ok = rtlil == cleared
                print(
                    "roundtrip: {} synthesis: {}{}".format(
                        label,
                        "from the RTL" if rtlil else "the netlist, copied",
                        "" if ok else ", NOT what config.mk and the make line ask",
                    )
                )
                failures += not ok
            seeds = stage != "floorplan"
            same, lines = compare(openroad, bazel_odbs[rel], made, seeds=seeds)
            print("roundtrip: {} {}: {}".format(label, stage, lines[-1]))
            for l in lines:
                if l.startswith("roundtrip: note: "):
                    print("  " + l)
            if not same:
                failures += 1
                for l in lines[:-1][:20]:
                    print("  " + l)
            macro = re.search(r"^snapshot_macro \{([^}]*)\}", _read(dest, rel), re.M)
            if macro:
                same, lines = compare(
                    openroad, bazel_odbs[rel], made, macro.group(1), seeds
                )
                ok = not same and any(macro.group(1) in l for l in lines)
                print(
                    "roundtrip: {} negative control, {} moved one site: {}".format(
                        label, macro.group(1), "fails, as it must" if ok else "PASSES"
                    )
                )
                failures += not ok

            literal = sorted(k for k, v in e.items() if LITERAL.match(v))
            r = subprocess.run(
                [runner, "DESIGN_CONFIG=" + path, "WORK_HOME=" + work]
                + ["print-" + k for k in literal],
                cwd=main_dir,
                env=make_env(),
                capture_output=True,
                text=True,
            )
            # ORFS's print-%: "VAR: value"
            seen = dict(
                re.match(r"^(\w+): ?(.*)$", l).groups()
                for l in r.stdout.splitlines()
                if re.match(r"^\w+:", l)
            )
            wrong = [
                "{} is {!r} in config.mk, {!r} to make".format(k, e[k], seen.get(k))
                for k in literal
                if k not in seen or seen[k].split() != e[k].split()
            ]
            print(
                "roundtrip: {} config.mk: {} literal values, {} differ".format(
                    label, len(literal), len(wrong)
                )
            )
            for w in wrong:
                print("  " + w)
            failures += bool(wrong)
    except Refused as e:
        print("roundtrip: " + str(e), file=sys.stderr)
        return 1
    print(
        "roundtrip: {}".format("PASS" if failures == 0 else "FAIL, {}".format(failures))
    )
    return 1 if failures else 0


def _read(dest, rel):
    path = os.path.join(dest, rel, "macro_placement.tcl")
    return open(path).read() if os.path.exists(path) else ""


if __name__ == "__main__":
    sys.exit(main())
