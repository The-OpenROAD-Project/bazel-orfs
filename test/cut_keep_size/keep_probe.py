"""Which modules SYNTH_MINIMUM_KEEP_SIZE keeps, today and with macros at cost 0.

    keep_probe.py --out DIR --jobs N <design>=<synth target>[:frontend] ...

Run from the bazel-orfs root with Bazel free. For each design, Bazel lays
out a dirty-lane synthesis tree once (`//:dirty start <flow> synth`);
then, in two copies of it, yosys runs ORFS's synthesis up to the keep
decision and writes the modules kept, without the blackboxes:

  today  ORFS's scripts as they are
  zero   convert_liberty_areas gives a blackbox macro a gate cost of 0

ORFS's scripts in a tree are links into Bazel's shared repository cache:
each is replaced by a copy before it is edited. Each design synthesises
with its own frontend as ORFS sets it ("slang" or "", yosys's own),
since the frontend names the modules. Writes DIR/<design>/{today,zero}.txt
and DIR/keeps.json.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

PROBE = """
    if { [info exists ::env(KEEP_PROBE_OUT)] } {
      set f [open $::env(KEEP_PROBE_OUT) w]
      puts $f [tee -q -s result.string select -list-mod A:keep_hierarchy A:blackbox %d]
      close $f
      exit 0
    }
"""

KEEP = "    keep_hierarchy -min_cost $ungroup_threshold\n"
GATE = "    rtlil::set_attr -mod -uint $box gate_cost_equivalent $gate_eq\n"
ZERO = "    if { [rtlil::has_attr -mod $box blackbox] } { set gate_eq 0 }\n"


def own_copy(path):
    """Replace a link into the shared cache by a copy, before editing."""
    if os.path.islink(path):
        real = os.path.realpath(path)
        os.unlink(path)
        shutil.copyfile(real, path)


def edit(path, old, new):
    own_copy(path)
    with open(path) as f:
        text = f.read()
    if text.count(old) != 1:
        raise SystemExit("%s: expected %r once" % (path, old.strip()))
    with open(path, "w") as f:
        f.write(text.replace(old, new))


def scripts(tree):
    hits = []
    for root, _, files in os.walk(tree):
        if root.endswith("flow/scripts") and "synth.tcl" in files:
            hits.append(root)
    if len(hits) != 1:
        raise SystemExit("%s: %d flow/scripts directories" % (tree, len(hits)))
    return hits[0]


def results_rel(tree):
    out = subprocess.run(
        [os.path.join(tree, "make.stage"), "print-RESULTS_DIR"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.decode()
    m = re.search(r"^RESULTS_DIR: (\S+)", out, re.M)
    if not m:
        raise SystemExit("%s: no RESULTS_DIR" % tree)
    return m.group(1)


def probe(name, base, frontend, mode, out):
    tree = os.path.join(out, name, mode)
    shutil.rmtree(tree, ignore_errors=True)
    subprocess.check_call(["cp", "-a", base, tree])
    s = scripts(tree)
    edit(os.path.join(s, "synth.tcl"), KEEP, KEEP + PROBE)
    if mode == "zero":
        edit(os.path.join(s, "synth_preamble.tcl"), GATE, ZERO + GATE)
    with open(os.path.join(tree, "_main", "config.mk"), "a") as f:
        f.write(
            "\n# keep_probe: yosys, the design's own frontend\n"
            "export SYNTH_USE_SYN=0\nexport SYNTH_HDL_FRONTEND=%s\n"
            "export SYNTH_NUM_PARTITIONS=\n" % frontend
        )
    listing = os.path.join(out, name, mode + ".txt")
    log = os.path.join(out, name, mode + ".log")
    env = dict(os.environ, KEEP_PROBE_OUT=os.path.abspath(listing))
    with open(log, "w") as f:
        rc = subprocess.call(
            [os.path.join(tree, "make"), "do-yosys-canonicalize", "do-yosys"],
            stdout=f,
            stderr=subprocess.STDOUT,
            env=env,
        )
    if not os.path.exists(listing):
        return name, mode, None, "no keep decision (exit %d); see %s" % (rc, log)
    with open(listing) as f:
        kept = sorted(l.strip().lstrip("\\") for l in f if l.strip())
    return name, mode, kept, None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("designs", nargs="+")
    args = ap.parse_args(argv)
    out = os.path.abspath(args.out)
    todo = []
    for d in args.designs:
        name, _, rest = d.partition("=")
        target, _, frontend = rest.rpartition(":")
        base = os.path.join(out, name, "base")
        if not os.path.isdir(base):
            os.makedirs(os.path.join(out, name), exist_ok=True)
            with open(os.path.join(out, name, "dirty.log"), "w") as f:
                rc = subprocess.call(
                    [
                        "bazelisk",
                        "run",
                        "//:dirty",
                        "--",
                        "start",
                        target,
                        "--dir",
                        base,
                    ],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                )
            if rc:
                print("%s: dirty start failed (exit %d)" % (name, rc), flush=True)
                continue
        todo += [(name, base, frontend, mode) for mode in ("today", "zero")]
        print("%s: tree ready" % name, flush=True)
    results = {}
    with ThreadPoolExecutor(args.jobs) as pool:
        for name, mode, kept, err in pool.map(lambda t: probe(*t, out), todo):
            results.setdefault(name, {})[mode] = kept if err is None else {"error": err}
            print("%s %s: %s" % (name, mode, err or "%d kept" % len(kept)), flush=True)
    with open(os.path.join(out, "keeps.json"), "w") as f:
        json.dump(results, f, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
