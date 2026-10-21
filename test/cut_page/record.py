"""Record the module-cut search's page: a PNG every 10 s, headless.

    bazelisk run //test/cut_page:record -- <flow> out.json frames/
        [--every 10] [--size 1600x760] [-- generate_cut options...]

Runs generate_cut, whose page a human can watch as usual from its link,
and Chrome for Testing's headless shell (a dev-only download,
MODULE.bazel) takes a screenshot of it every --every seconds (a headless
screenshot has no address bar: no address or token reaches a frame),
and the page's DOM beside it, until the search is done; then a last
frame, and the search is stopped.

frames/report.json says, from the DOM, which arms the page showed
running and which finished, and every console message the page logged.
It exits 1 when the page logged an error, or when an arm finished
without the page having shown it running: a search too fast for the
page to show is a page that does not show the search.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from python.runfiles import runfiles

ROW = re.compile(r"<tr[^>]*>\s*<td>(\d+)</td>(.*?)</tr>", re.S)


def chrome(exe, profile, url, size, what, out=None):
    """One headless load of url: a screenshot or the DOM; (stdout, console)."""
    w, h = size.split("x")
    cmd = [
        exe,
        "--headless",
        "--hide-scrollbars",
        "--window-size=%s,%s" % (w, h),
        "--user-data-dir=" + profile,
        "--enable-logging=stderr",
        "--v=0",
    ]
    # The shell captures at the page's load event, before its WebSocket has
    # delivered any state (--timeout only caps the wait); virtual time runs
    # the page's pending work, the state and its render, before the capture.
    cmd.append("--virtual-time-budget=3000")
    if what == "png":
        cmd.append("--screenshot=" + out)
    else:
        cmd.append("--dump-dom")
    cmd.append(url)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    console = [
        l
        for l in p.stderr.decode("utf-8", "replace").splitlines()
        if "CONSOLE" in l or "Uncaught" in l
    ]
    return p.stdout.decode("utf-8", "replace"), console


def arm_states(dom):
    """{arm id: "running" | "done" | "failed"} from the page's arm table."""
    out = {}
    for m in ROW.finditer(dom):
        cells = m.group(2)
        if "status-run" in cells:
            out[int(m.group(1))] = "running"
        elif "status-fail" in cells:
            out[int(m.group(1))] = "failed"
        else:
            out[int(m.group(1))] = "done"
    return out


def main(argv):
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1 :]
    else:
        extra = []
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("flow")
    ap.add_argument("out")
    ap.add_argument("frames")
    ap.add_argument("--every", type=float, default=10.0)
    ap.add_argument("--size", default="1600x760")
    ap.add_argument("--chrome", required=True, help=argparse.SUPPRESS)
    ap.add_argument("--generate-cut", required=True, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    r = runfiles.Create()
    exe = r.Rlocation(args.chrome)
    gen = r.Rlocation(args.generate_cut)
    cwd = os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())
    frames = os.path.join(cwd, args.frames)
    shutil.rmtree(frames, ignore_errors=True)
    os.makedirs(frames)
    profile = tempfile.mkdtemp(prefix="cut_page_profile.", dir=frames)

    env = dict(os.environ)
    env.update(r.EnvVars())
    proc = subprocess.Popen(
        [gen, args.flow, args.out, "--idle", "0"] + extra,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=cwd,
    )
    url = None
    done = threading.Event()
    failed = []
    log = open(os.path.join(frames, "generate_cut.log"), "w")

    def read():
        nonlocal url
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace")
            log.write(line)
            log.flush()
            m = re.search(r"generate_cut: (http://\S+)", line)
            if m:
                url = m.group(1)
            if "best keep list" in line:
                done.set()
            if "Traceback" in line or re.search(r"generate_cut: .*failed", line):
                failed.append(line.strip())
                done.set()
        done.set()

    t = threading.Thread(target=read)
    t.daemon = True
    t.start()
    while url is None and not done.is_set():
        time.sleep(0.2)
    if url is None:
        sys.exit("record: generate_cut printed no link; see %s" % log.name)
    print("record: the page, live: %s" % url, flush=True)

    seen = {}  # arm id -> set of states the page showed
    console = []
    n = 0
    finishing = False
    while True:
        t0 = time.time()
        n += 1
        png = os.path.join(frames, "frame-%04d.png" % n)
        _, c1 = chrome(exe, profile, url, args.size, "png", png)
        dom, c2 = chrome(exe, profile, url, args.size, "dom")
        console += ["frame %d: %s" % (n, l) for l in c1 + c2]
        for arm, st in arm_states(dom).items():
            seen.setdefault(arm, set()).add(st)
        print("record: frame %d, %d arms shown" % (n, len(seen)), flush=True)
        if finishing:
            break
        if done.is_set():
            finishing = True  # one last frame of the finished search
            continue
        time.sleep(max(0.0, args.every - (time.time() - t0)))

    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(profile, ignore_errors=True)
    shutil.copy(png, os.path.join(frames, "final.png"))

    never_running = sorted(a for a, s in seen.items() if "running" not in s)
    errors = [l for l in console if "ERROR" in l or "Uncaught" in l]
    report = {
        "frames": n,
        "arms_shown": sorted(seen),
        "never_shown_running": never_running,
        "console": console,
        "search_failed": failed,
    }
    with open(os.path.join(frames, "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(
        "record: %d frames; %d arms; never shown running: %s; console errors: %d"
        % (n, len(seen), never_running or "none", len(errors))
    )
    return 1 if (errors or never_running or failed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
