"""Search a flow's module cuts: which modules synthesis keeps.

    bazelisk run //tools/macro_select/cut:generate_cut -- <flow> out.json
        [--jobs N] [--port P] [--target-frac F] [--fresh]

<flow> is an orfs_flow's label, //pkg:name, or its synthesis target,
//pkg:name_synth. The web page starts first: its link, with a token,
reachable over a VPN (the address the ssh session came in on), is
printed before anything is built, and shows the search as it runs.

Bazel builds what the search needs and is then out of the loop: two
dirty-lane trees (.claude/skills/dirty-lane), the flow's synthesis and
its floorplan, laid out once under tmp/cut/<pkg>/<name>. Each arm is a
copy of the two, synthesised with its keep list by yosys and
floorplanned by ORFS's make, and its keep census taken on the floorplan
by worker.py, on OpenROAD's Python bindings. Numbers from the search are
dirty-lane numbers: the winner's keep list goes into the flow's BUILD and
a clean build confirms it.

out.json: the best keep list, every arm measured with what the census
predicted for it, and the census of each.
"""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time

import cut
import odbdebug
import serve

SYNTH_STAGE = [
    "do-yosys-canonicalize",
    "do-yosys",
    "{results}/1_2_yosys.sdc",
    "do-1_synth",
]


def runfiles_dir():
    d = os.environ.get("RUNFILES_DIR")
    if d:
        return d
    here = os.path.abspath(__file__)
    while here != "/":
        if here.endswith(".runfiles"):
            return here
        here = os.path.dirname(here)
    raise RuntimeError("generate_cut: no runfiles directory; run it with bazelisk run")


def runfile(path):
    for repo in ("_main", "bazel-orfs+"):
        p = os.path.join(runfiles_dir(), repo, path)
        if os.path.exists(p):
            return p, repo
    raise RuntimeError("generate_cut: %s is not in the runfiles" % path)


def flow_label(label):
    if label.endswith("_synth"):
        return label[: -len("_synth")]
    return label


def tree_dir(ws, flow):
    pkg, _, name = flow.partition(":")
    pkg = pkg.lstrip("@").replace("//", "/").strip("/")
    return os.path.join(ws, "tmp", "cut", pkg, name)


def clock_period(sdc):
    with open(sdc) as f:
        for line in f:
            m = re.search(r"create_clock\b.*-period\s+(\S+)", line)
            if m:
                return float(m.group(1))
    raise ValueError("%s has no create_clock -period" % sdc)


def scrub(text, ws, home):
    """text with no local path: the page may be watched, recorded or
    published, so the workspace's paths are relative and the home
    directory is ~."""
    text = text.replace(ws + os.sep, "").replace(ws, ".")
    return text.replace(home, "~") if home not in ("", "/") else text


class Search(object):
    def __init__(self, args, ws):
        self.args = args
        self.ws = ws
        self.flow = flow_label(args.flow)
        self.dir = tree_dir(ws, self.flow)
        self.lock = threading.Lock()
        self.arms = []  # in launch order
        self.results = {}  # arm key -> result, None while running
        self.census = {}  # arm key -> parsed census
        self.queue = []
        self.phase = "starting"
        self.note = ""
        self.types = []
        self.design = None
        self.clock = None
        self.target = None
        self.server = None
        self.done = 0
        worker, repo = runfile("tools/macro_select/cut/worker")
        self.worker = worker
        self.census_tcl = runfile("tools/macro_select/keep_census.tcl")[0]
        self.dump_env = runfile("tools/macro_select/cut/dump_env.tcl")[0]
        self.dirty = "//:dirty" if repo == "_main" else "@bazel-orfs//:dirty"

    # --- the page's view ---------------------------------------------------

    def state(self):
        with self.lock:
            b = self.best_keep()
            return {
                "flow": self.flow,
                "design": self.design,
                "phase": self.phase,
                "note": self.note,
                "clock": self.clock,
                "target": self.target,
                "types": self.types,
                "best": list(b) if b is not None else None,
                "arms": [{k: v for k, v in a.items() if k != "dir"} for a in self.arms],
                "queue": list(self.queue),
                "viewers": self.server.viewers() if self.server else 0,
            }

    def local(self, text):
        return scrub(text, self.ws, os.path.expanduser("~"))

    def changed(self, **kw):
        if "note" in kw:
            kw["note"] = self.local(kw["note"])
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)
        if self.server:
            self.server.push()

    # --- Bazel builds the trees, once ----------------------------------------

    def bazel_trees(self):
        for stage in ("synth", "floorplan"):
            d = os.path.join(self.dir, stage)
            if os.path.isdir(d) and not self.args.fresh:
                continue
            self.changed(note="bazel: laying out the %s tree" % stage)
            cmd = [
                "bazelisk",
                "run",
                self.dirty,
                "--",
                "start",
                self.flow,
                stage,
                "--dir",
                d,
                "--fresh",
            ]
            log = os.path.join(self.dir, "%s.bazel.log" % stage)
            os.makedirs(self.dir, exist_ok=True)
            with open(log, "w") as f:
                rc = subprocess.call(
                    cmd, cwd=self.ws, stdout=f, stderr=subprocess.STDOUT
                )
            if rc:
                raise RuntimeError(
                    "%s failed (exit %d); see %s" % (" ".join(cmd), rc, log)
                )
        fp = os.path.join(self.dir, "floorplan")
        env_json = os.path.join(self.dir, "env.json")
        self.make(
            fp,
            ["run", "RUN_SCRIPT=" + self.dump_env, "DUMP_ENV_OUT=" + env_json],
            os.path.join(self.dir, "env.log"),
        )
        with open(env_json) as f:
            env = json.load(f)["env"]
        self.env_json = env_json
        self.results_rel = env["RESULTS_DIR"]
        main = os.path.join(fp, "_main")
        # the module hierarchy from yosys's own canonicalisation, in a copy
        # of the synthesis tree: a flow synthesised by OpenROAD
        # (SYNTH_USE_SYN) has an empty placeholder for it
        hier_tree = os.path.join(self.dir, "hierarchy")
        shutil.rmtree(hier_tree, ignore_errors=True)
        subprocess.check_call(["cp", "-a", os.path.join(self.dir, "synth"), hier_tree])
        with open(os.path.join(hier_tree, "_main", "config.mk"), "a") as f:
            f.write(
                "\n# generate_cut: yosys's canonicalisation\nexport SYNTH_USE_SYN=0\n"
            )
        self.make(
            hier_tree,
            ["do-yosys-canonicalize"],
            os.path.join(self.dir, "hierarchy.log"),
        )
        rtlil = os.path.join(
            hier_tree, "_main", self.results_rel, "1_1_yosys_canonicalize.rtlil"
        )
        if not os.path.getsize(rtlil):
            raise RuntimeError(
                "%s is empty; see %s" % (rtlil, os.path.join(self.dir, "hierarchy.log"))
            )
        with open(rtlil) as f:
            hier = cut.rtlil_hierarchy(f)
        design = env["DESIGN_NAME"]
        clock = clock_period(os.path.join(main, self.results_rel, "1_synth.sdc"))
        self.groups = cut.module_groups(cut.types_under(hier, design))
        self.changed(
            design=design,
            types=sorted(self.groups),
            clock=clock,
            target=round(clock * self.args.target_frac, 1),
        )

    def make(self, tree, targets, log):
        with open(log, "w") as f:
            rc = subprocess.call(
                [os.path.join(tree, "make")] + targets,
                stdout=f,
                stderr=subprocess.STDOUT,
            )
        if rc:
            raise ArmFailed(
                "make %s exit %d; see %s"
                % (" ".join(targets), rc, os.path.relpath(log, self.ws))
            )

    # --- one arm -------------------------------------------------------------

    def run_arm(self, arm):
        key = self.key(arm)
        d = arm["dir"]
        try:
            self.step(arm, "copying the trees")
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
            synth = os.path.join(d, "synth")
            fp = os.path.join(d, "floorplan")
            subprocess.check_call(["cp", "-a", os.path.join(self.dir, "synth"), synth])
            subprocess.check_call(["cp", "-a", os.path.join(self.dir, "floorplan"), fp])
            with open(os.path.join(synth, "_main", "config.mk"), "a") as f:
                if arm.get("control"):
                    # the flow's own keep settings, synthesised by yosys as
                    # every arm is
                    f.write(
                        "\n# generate_cut arm %d: the flow's own keep settings\n"
                        "export SYNTH_USE_SYN=0\n" % arm["id"]
                    )
                else:
                    f.write(
                        "\n# generate_cut arm %d: yosys, only these modules kept\n"
                        "export SYNTH_USE_SYN=0\n"
                        "export SYNTH_HIERARCHICAL=1\n"
                        "export SYNTH_MINIMUM_KEEP_SIZE=1000000000\n"
                        "export SYNTH_KEEP_MODULES=%s\n"
                        % (
                            arm["id"],
                            " ".join(
                                m.replace("$", "$$")
                                for t in arm["keep"]
                                for m in self.groups[t]
                            ),
                        )
                    )
            self.step(arm, "synthesis")
            t0 = time.time()
            self.make(
                synth,
                [t.format(results=self.results_rel) for t in SYNTH_STAGE],
                os.path.join(d, "synth.log"),
            )
            t_syn = time.time() - t0
            for name in ("1_synth.odb", "1_synth.sdc"):
                shutil.copy(
                    os.path.join(synth, "_main", self.results_rel, name),
                    os.path.join(fp, "_main", self.results_rel, name),
                )
            self.step(arm, "floorplan", t_syn=round(t_syn, 1))
            t0 = time.time()
            self.make(fp, ["do-floorplan"], os.path.join(d, "floorplan.log"))
            t_fp = time.time() - t0
            self.step(arm, "census", t_fp=round(t_fp, 1))
            out = os.path.join(d, "census.tsv")
            env = dict(os.environ, RUNFILES_DIR=runfiles_dir())
            with open(os.path.join(d, "census.log"), "w") as f:
                rc = subprocess.call(
                    [
                        self.worker,
                        "--tree",
                        fp,
                        "--env",
                        self.env_json,
                        "--census-tcl",
                        self.census_tcl,
                        "--target",
                        str(self.target),
                        "--out",
                        out,
                    ],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
            if rc:
                raise ArmFailed(
                    "census exit %d; see %s"
                    % (rc, os.path.relpath(os.path.join(d, "census.log"), self.ws))
                )
            with open(out) as f:
                c = cut.parse_census(f)
            top = [m for m in c["module"] if m["inst"] == "(top)"]
            result = {
                "P": c["period"]["worst"],
                "area": top[0]["area"],
                "t_syn": round(t_syn, 1),
            }
            with self.lock:
                if arm.get("control"):
                    # what the flow's settings kept, read off the census
                    kept = set()
                    for m in c["module"]:
                        t = cut.rtl_type(m["master"], self.types)
                        if m["inst"] != "(top)" and t is not None:
                            kept.add(t)
                    arm["keep"] = sorted(kept)
                self.census[key] = c
                self.results[key] = result
                arm.update(result)
                arm["status"] = "done"
                arm["step"] = ""
                arm["census"] = c
                self.done += 1
                arm["done_seq"] = self.done
        except ArmFailed as e:
            with self.lock:
                self.results[key] = {"P": None, "failed": self.local(str(e))}
                arm["status"] = "failed"
                arm["step"] = self.local(str(e))
        self.replan()

    def step(self, arm, what, **kw):
        with self.lock:
            arm["step"] = what
            arm.update(kw)
        if self.server:
            self.server.push()

    # --- the search ------------------------------------------------------------

    CONTROL = ("@control",)

    def key(self, arm):
        return self.CONTROL if arm.get("control") else cut.arm_key(arm["keep"])

    def best_keep(self):
        """The best arm's keep list as a key: the control's is what its
        census says the flow's settings kept."""
        b = cut.best(self.results)
        if b == self.CONTROL:
            ctl = [a for a in self.arms if a.get("control")][0]
            return cut.arm_key(ctl["keep"])
        return b

    def census_of(self, key):
        if key in self.census:
            return self.census[key]
        for a in self.arms:
            if a.get("control") and cut.arm_key(a["keep"] or []) == key:
                return self.census.get(self.CONTROL)
        return None

    def replan(self):
        with self.lock:
            b = self.best_keep()
            # a keep set the control already measured is not tried again
            seen = dict(self.results)
            for a in self.arms:
                if a.get("control") and a["keep"] is not None:
                    seen.setdefault(cut.arm_key(a["keep"]), self.results[self.CONTROL])
            q = cut.plan(self.types, seen, b, self.census_of)
            self.queue = q
        if self.server:
            self.server.push()

    def launch(self, nxt, control=False):
        with self.lock:
            n = len(self.arms)
            name = "control" if control else ("+".join(nxt["keep"]) or "flat")
            arm = {
                "id": n,
                "control": control,
                "keep": None if control else nxt["keep"],
                "pred": None if control else nxt["pred"],
                "pred_sum": None if control else nxt["pred_sum"],
                "why": "the flow's own keep settings" if control else nxt["why"],
                "status": "running",
                "step": "",
                "dir": os.path.join(self.dir, "arms", ("%02d-%s" % (n, name))[:80]),
            }
            self.arms.append(arm)
            self.results[self.key(arm)] = None
            if not control:
                self.queue = [x for x in self.queue if x is not nxt]
        t = threading.Thread(target=self.run_arm, args=(arm,))
        t.daemon = True
        t.start()
        return t

    def search(self):
        self.changed(phase="searching", note="")
        self.replan()
        threads = [self.launch(None, control=True)]
        while True:
            with self.lock:
                running = [a for a in self.arms if a["status"] == "running"]
                q = list(self.queue)
                waiting_for_base = any(
                    not a.get("control")
                    and cut.arm_key(a["keep"]) == cut.arm_key(self.types)
                    for a in running
                )
            if not running and (not q or len(self.arms) >= self.args.max_arms):
                break
            if len(self.arms) >= self.args.max_arms:
                q = []
            if q and len(running) < self.args.jobs and not waiting_for_base:
                threads.append(self.launch(q[0]))
                continue
            time.sleep(0.5)
        for t in threads:
            t.join()

    def write_out(self, path):
        with self.lock:
            b = self.best_keep()
            out = {
                "flow": self.flow,
                "design": self.design,
                "engine": "yosys",
                "clock_ps": self.clock,
                "target_ps": self.target,
                "types": self.types,
                "keep": list(b) if b is not None else None,
                "caveat": "from dirty-lane trees, not a clean build: floorplan, no wire",
                "arms": [
                    {
                        k: a.get(k)
                        for k in (
                            "id",
                            "control",
                            "keep",
                            "status",
                            "P",
                            "area",
                            "t_syn",
                            "t_fp",
                            "pred",
                            "pred_sum",
                            "why",
                            "step",
                            "census",
                        )
                    }
                    for a in self.arms
                ],
            }
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
            f.write("\n")


class ArmFailed(Exception):
    pass


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("flow")
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument(
        "--target-frac",
        type=float,
        default=0.8,
        help="census target as a fraction of the clock period",
    )
    ap.add_argument("--fresh", action="store_true", help="lay the trees out again")
    ap.add_argument(
        "--max-arms", type=int, default=40, help="stop after this many arms"
    )
    ap.add_argument(
        "--idle",
        type=float,
        default=300,
        help="once the search is over, exit when no browser has been connected"
        " for this many seconds, counted from the first one leaving; 0 serves"
        " until Ctrl-C",
    )
    args = ap.parse_args(argv)

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not ws:
        sys.exit("generate_cut: run it with bazelisk run")
    cwd = os.environ.get("BUILD_WORKING_DIRECTORY", ws)
    out = os.path.join(cwd, args.out)

    s = Search(args, ws)
    page_path = runfile("tools/macro_select/cut/page.html")[0]

    def page():
        # read per request: an edit to the page shows on the next load
        with open(page_path) as f:
            return f.read()

    bind = odbdebug.gui_bind() or "127.0.0.1"
    token = secrets.token_urlsafe(24)
    s.server = serve.Server(bind, args.port, token, page, s.state, log=say)
    s.server.start()
    print(
        "generate_cut: http://%s:%d/?token=%s" % (bind, s.server.port, token),
        flush=True,
    )

    try:
        s.bazel_trees()
        s.search()
        s.write_out(out)
        b = s.best_keep()
        s.changed(phase="done", note="wrote %s" % out)
        print(
            "generate_cut: best keep list %s; wrote %s" % (list(b) if b else None, out)
        )
    except Exception as e:
        s.changed(phase="failed", note=str(e))
        print("generate_cut: %s" % e, file=sys.stderr)
        raise
    finally:
        linger(s.server, args.idle)
    return 0


def say(msg):
    print("generate_cut: %s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def linger(server, idle):
    """Serve the finished search until no browser has been connected for
    idle seconds, after the first one left; until Ctrl-C if idle is 0."""
    if idle:
        say(
            "the page stays up until no browser has been connected for %.0f s"
            " (heartbeat every %.0f s); Ctrl-C to stop" % (idle, server.PING_EVERY)
        )
    else:
        say("the page stays up; Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
            gone = server.idle_for(server.clock())
            if idle and gone is not None and gone >= idle:
                say("no browser for %.0f s; exiting" % gone)
                return
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
