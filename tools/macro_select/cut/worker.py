"""One arm's census, in this process, on OpenROAD's Python bindings.

    worker.py --tree ARM/floorplan --env env.json --census-tcl keep_census.tcl
              --target PS --out census.tsv [--serve PORT]

env.json is what the floorplan tree's make gives openroad (dump_env.tcl),
taken once from the template tree: every arm is a copy of it, so its
relative paths hold in any arm. The design is loaded as the flow's own
open does (load.tcl), so the timing is the flow's, and buffered by
repair_design -pre_placement before the census: a floorplan has not been
buffered yet, and on riscv32i an unbuffered net of 535 loads made the
worst period 3,981 ps against a 950 ps clock, 854 ps once buffered. The
census measures what the keep set did to the logic, not missing buffers. With --serve the
process stays, the OpenROAD web viewer on 127.0.0.1:PORT on the arm's
floorplan, until the viewer is told to exit.
"""

import argparse
import json
import os
import sys

import _openroad_loader  # noqa: F401  (must precede the wrapper import)
import ord_py


def tcl_quote(s):
    return "{" + s + "}"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tree", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--census-tcl", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--serve", type=int)
    args = ap.parse_args(argv)

    with open(args.env) as f:
        env = json.load(f)["env"]
    os.environ.update(env)
    os.environ["CENSUS_TARGET"] = args.target
    os.environ["CENSUS_OUT"] = os.path.abspath(args.out)
    os.chdir(os.path.join(args.tree, "_main"))

    tech = ord_py.Tech()
    if not ord_py.tcl_library_init():
        sys.stderr.write("census: Tcl's library did not initialise\n")
        return 1
    design = ord_py.Design(tech)
    # evalTclString returns the result, not whether it was an error
    script = (
        "if { [catch {"
        " source $::env(SCRIPTS_DIR)/load.tcl;"
        " load_design 2_floorplan.odb 2_floorplan.sdc;"
        " repair_design -pre_placement;"
        " source %s;"
        " keep_census"
        ' } msg] } { return "ERROR: $msg" }; return ok'
    ) % tcl_quote(os.path.abspath(args.census_tcl))
    result = design.evalTclString(script)
    if result != "ok":
        sys.stderr.write("census: %s\n" % result)
        return 1
    if args.serve is not None:
        design.evalTclString(
            "web::web_server_cmd %d 127.0.0.1 0; web::web_server_wait_cmd" % args.serve
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
