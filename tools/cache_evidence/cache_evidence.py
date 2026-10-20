"""Is this target a remote cache hit here? Asked without building it.

`capture` runs the build in a fresh output base, so nothing is hidden by
the local action cache, and never lets an action execute: a remote cache
miss is spawned sandboxed and killed the moment it appears, so it fails in
a second, logged, and `--keep_going` carries the build on to every other
action whose inputs exist. Remote hits never execute and are unaffected;
the strategy is not part of any cache key. Actions behind a miss cannot be
keyed, since their inputs were never produced; they are listed as
`not_reached` so their absence is never mistaken for a hit. An action so
short that it finished before it could be killed (writing a variables
file) is listed as `ran`: not a hit, and its result stays local since
uploading is off. A capture is therefore safe on a machine that only
consumes the cache: it downloads the inputs of each miss and computes
nothing that takes longer than a blink.

It prints the counts, every miss and every action left unreached, or
`every action is a remote cache hit`; it exits 1 on a miss or an unreached
action.
"""

import argparse
import datetime
import io
import os
import re
import shutil
import json
import stat
import subprocess
import sys

from killer import Killer, sandboxed_pids  # noqa: F401, re-exported for the tests

# ---------------------------------------------------------------------------
# Protobuf wire format, just enough for ExecLogEntry (src/main/protobuf/
# spawn.proto in Bazel). The compact log is a zstd stream of
# varint-length-delimited ExecLogEntry messages.


def _varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _fields(buf):
    """Yield (field number, value) for a message; LEN fields as bytes."""
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = _varint(buf, pos)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, pos = _varint(buf, pos)
        elif wire == 2:
            n, pos = _varint(buf, pos)
            val = buf[pos : pos + n]
            pos += n
        elif wire == 1:
            val = buf[pos : pos + 8]
            pos += 8
        elif wire == 5:
            val = buf[pos : pos + 4]
            pos += 4
        else:
            raise ValueError("unsupported wire type %d" % wire)
        yield num, val


def _packed_uints(val):
    """A repeated uint32: packed (bytes) or a single unpacked varint."""
    if isinstance(val, int):
        return [val]
    out = []
    pos = 0
    while pos < len(val):
        v, pos = _varint(val, pos)
        out.append(v)
    return out


def _messages(data):
    """Split a decompressed log into ExecLogEntry payloads.

    A log cut short by an interrupted build ends in a partial message;
    that one is dropped rather than failing the whole summary.
    """
    pos = 0
    end = len(data)
    while pos < end:
        try:
            n, body = _varint(data, pos)
        except IndexError:
            return
        if body + n > end:
            return
        yield data[body : body + n]
        pos = body + n


# Entry kinds, keyed by the ExecLogEntry oneof field number.
_FILE, _DIR, _SYMLINK, _INPUT_SET, _SPAWN, _SYMLINK_SET, _RUNFILES = (
    3,
    4,
    5,
    6,
    7,
    9,
    10,
)


def _spawns(data):
    """The spawn entries of one compact execution log, and a function
    that resolves an output's entry id to its path."""
    entries = {}
    spawns = []
    for msg in _messages(data):
        eid, kind, body = 0, None, None
        for num, val in _fields(msg):
            if num == 1:
                eid = val
            elif num >= 2:
                kind, body = num, val
        if kind == _SPAWN:
            spawns.append(body)
        elif kind is not None:
            entries[eid] = body

    def path(eid):
        for num, val in _fields(entries[eid]):
            if num == 1:
                return val.decode()
        return ""

    return spawns, path


def _short(path):
    """bazel-out/k8-fastbuild/bin/x -> k8-fastbuild:x"""
    m = re.match(r"bazel-out/([^/]+)/bin/(.*)", path)
    return "%s:%s" % m.groups() if m else path


def _spawn_fields(buf):
    s = {
        "outputs": [],
        "label": "",
        "mnemonic": "",
        "exit": 0,
        "status": "",
        "cache_hit": False,
    }
    for num, val in _fields(buf):
        if num == 6:
            for n2, v2 in _fields(val):
                if n2 == 5:
                    s["outputs"].append(("id", v2))
                elif n2 == 4:
                    s["outputs"].append(("path", v2.decode()))
        elif num == 7:
            s["label"] = val.decode()
        elif num == 8:
            s["mnemonic"] = val.decode()
        elif num == 9:
            s["exit"] = val
        elif num == 10:
            s["status"] = val.decode()
        elif num == 12:
            s["cache_hit"] = bool(val)
    return s


def summarize_log(data, scope):
    """The counts of a compact log, and (status, mnemonic, first output) of
    every spawn of a label under scope."""
    spawns, path = _spawns(data)
    counts = {"spawns": 0, "hit": 0, "ran": 0, "miss": 0, "outside": []}
    out = []
    for buf in spawns:
        s = _spawn_fields(buf)
        counts["spawns"] += 1
        if s["cache_hit"]:
            status = "hit"
        elif s["exit"] != 0 or s["status"]:
            status = "miss"
        else:
            status = "ran"
        counts[status] += 1
        outs = sorted(path(val) if kind == "id" else val for kind, val in s["outputs"])
        first = _short(outs[0]) if outs else s["label"]
        if s["label"].startswith(scope):
            out.append((status, s["mnemonic"] or "-", first))
        elif status != "hit":
            counts["outside"].append(
                "%s %s %s (outside --scope)" % (status, s["mnemonic"] or "-", first)
            )
    return counts, out


# Actions Bazel performs in-process and never logs as spawns: writing a
# file it composed itself, a symlink, a runfiles tree. Their absence from
# the execution log says nothing about the cache.
_INTERNAL = {
    "BinaryFileWrite",
    "ExecutableSymlink",
    "FileWrite",
    "Middleman",
    "RepoMappingManifest",
    "RunfilesTree",
    "SourceSymlinkManifest",
    "Symlink",
    "SymlinkTree",
    "TemplateExpand",
}


def _label(target):
    """//a/b -> //a/b:b, @@//a/b:c -> //a/b:c: the label as aquery prints it."""
    t = re.sub(r"^@@?(?=//)", "", target)
    if ":" not in t.split("//", 1)[-1]:
        t = "%s:%s" % (t, t.rstrip("/").rsplit("/", 1)[-1])
    return t


def graph_actions(aquery_json, scope, target=None, outputs=None):
    """(mnemonic, first output) of every in-scope action the target needs,
    from `aquery --output=jsonproto`, internal actions left out.

    `deps(target)` also holds actions of targets in the graph whose outputs
    the target never reads (a stage's `_deps` tarball, a generator's deploy
    jar), and the target itself has actions a build of it does not run
    (its own tarball). So only actions reachable through their inputs
    count, from the actions that produce `outputs` (the target's default
    outputs, `cquery --output=files`), or from every action of the target
    when no outputs are given; with neither, every in-scope action does."""
    g = json.loads(aquery_json) if aquery_json.strip() else {}
    fragments = {f["id"]: f for f in g.get("pathFragments", [])}
    paths = {}

    def path(fid):
        if fid in paths:
            return paths[fid]
        f = fragments[fid]
        parent = f.get("parentId")
        p = f["label"] if parent is None else path(parent) + "/" + f["label"]
        paths[fid] = p
        return p

    artifacts = {a["id"]: path(a["pathFragmentId"]) for a in g.get("artifacts", [])}
    targets = {t["id"]: t["label"] for t in g.get("targets", [])}
    actions = g.get("actions", [])
    depsets = {d["id"]: d for d in g.get("depSetOfFiles", [])}
    flat = {}

    def artifacts_of(root):
        if root in flat:
            return flat[root]
        result, stack, visited = set(), [root], set()
        while stack:
            d = stack.pop()
            if d in visited:
                continue
            visited.add(d)
            if d in flat:
                result |= flat[d]
                continue
            ds = depsets.get(d, {})
            result.update(ds.get("directArtifactIds", []))
            stack.extend(ds.get("transitiveDepSetIds", []))
        flat[root] = result
        return result

    producer = {}
    for i, a in enumerate(actions):
        for o in a.get("outputIds", []):
            producer[o] = i
    if outputs:
        wanted = set(outputs)
        needed = {
            producer[aid]
            for aid, path in artifacts.items()
            if path in wanted and aid in producer
        }
    elif target is not None:
        label = _label(target)
        needed = {
            i for i, a in enumerate(actions) if targets.get(a.get("targetId")) == label
        }
    else:
        needed = set(range(len(actions)))
    if outputs or target is not None:
        stack = list(needed)
        while stack:
            for dsid in actions[stack.pop()].get("inputDepSetIds", []):
                for art in artifacts_of(dsid):
                    j = producer.get(art)
                    if j is not None and j not in needed:
                        needed.add(j)
                        stack.append(j)
    out = []
    for i in sorted(needed):
        a = actions[i]
        if a.get("mnemonic", "") in _INTERNAL:
            continue
        if not targets.get(a.get("targetId"), "").startswith(scope):
            continue
        outs = sorted(artifacts[i] for i in a.get("outputIds", []))
        if outs:
            out.append((a.get("mnemonic", "-"), _short(outs[0])))
    return out


def not_reached(graph, spawns):
    """The in-scope actions of the graph the log has no spawn for."""
    logged = {out for _, _, out in spawns}
    return [
        "not_reached %s %s" % (mnemonic, out)
        for mnemonic, out in sorted(graph, key=lambda x: x[1])
        if out not in logged
    ]


def _decompress(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    import zstandard

    out = io.BytesIO()
    reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw))
    try:
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    except zstandard.ZstdError:
        pass  # an interrupted build leaves a truncated frame
    return out.getvalue()


def _rmtree(path):
    def onerror(func, p, _):
        os.chmod(os.path.dirname(p), stat.S_IRWXU)
        if os.path.isdir(p):
            os.chmod(p, stat.S_IRWXU)
        func(p)

    shutil.rmtree(path, onerror=onerror)


def capture_refusal(counts, build_text):
    """Why a capture must not be written, or None. A build that stopped
    before its first action -- a flag Bazel refused, a failed fetch --
    logs no spawns, and evidence of no spawns says nothing about the cache."""
    if counts["spawns"] > 0:
        return None
    errors = [l for l in build_text.splitlines() if l.startswith("ERROR:")]
    return errors[0] if errors else "the build logged no actions"


def capture_refusal(counts, build_text):
    """Why a capture says nothing, or None. A build that stopped before its
    first action -- a flag Bazel refused, a failed fetch -- logs no spawns,
    and no spawns says nothing about the cache."""
    if counts["spawns"] > 0:
        return None
    errors = [l for l in build_text.splitlines() if l.startswith("ERROR:")]
    return errors[0] if errors else "the build logged no actions"


def summary_lines(counts, spawns, unreached):
    """What a capture found: the counts, every miss and every action left
    unreached behind one."""
    out = [
        "spawns %d hit %d ran %d miss %d not_reached %d"
        % (
            counts["spawns"],
            counts["hit"],
            counts["ran"],
            counts["miss"],
            len(unreached),
        )
    ]
    for status, mnemonic, first in spawns:
        if status != "hit":
            out.append("%s %s %s" % (status, mnemonic, first))
    out += counts.get("outside", [])
    out += list(unreached)
    if counts["miss"] == 0 and counts["ran"] == 0 and not unreached:
        out.append("every action is a remote cache hit")
    return out


def _graph(bazel, ws, target, scope):
    """The in-scope actions of the graph as `aquery --output=jsonproto` and
    the target's default outputs from `cquery --output=files`, from the
    server that just built, then shut it down."""
    files = subprocess.run(
        bazel + ["cquery", "--output=files", "--curses=no", target],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    r = subprocess.run(
        bazel
        + [
            "aquery",
            "--output=jsonproto",
            "--curses=no",
            'filter("^%s", deps(%s))' % (re.escape(scope), target),
        ],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    subprocess.run(bazel + ["shutdown"], cwd=ws)
    for name, q in (("cquery", files), ("aquery", r)):
        if q.returncode != 0:
            raise SystemExit(
                "cache_evidence: %s of the graph failed:\n%s%s"
                % (name, q.stdout, q.stderr)
            )
    return r.stdout, files.stdout.split()


def cmd_capture(a):
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    work = os.path.join(ws, "tmp", "cache_evidence", stamp)
    ob = os.path.join(work, "output_base")
    log = os.path.join(work, "exec.log.zst")
    os.makedirs(work)
    bazel = [a.bazel, "--output_base=" + ob]
    build = bazel + [
        "build",
        a.target,
        "--keep_going",
        "--remote_download_minimal",
        "--remote_upload_local_results=false",
        "--execution_log_compact_file=" + log,
        "--curses=no",
        # Every miss runs in a sandbox directory under the output base,
        # which is how the killer recognizes it. Not part of any key.
        "--spawn_strategy=sandboxed",
    ]
    sys.stderr.write("cache_evidence: %s\n" % " ".join(build))
    killer = Killer(ob)
    killer.start()
    try:
        with open(os.path.join(work, "build.txt"), "w") as out:
            subprocess.call(build, cwd=ws, stdout=out, stderr=subprocess.STDOUT)
    finally:
        killer.stop()
    if killer.killed:
        sys.stderr.write(
            "cache_evidence: killed %d process(es) of actions the cache did"
            " not have\n" % len(killer.killed)
        )
    counts, spawns = summarize_log(_decompress(log), a.scope)
    with open(os.path.join(work, "build.txt")) as fh:
        refusal = capture_refusal(counts, fh.read())
    if refusal:
        subprocess.run(bazel + ["shutdown"], cwd=ws)
        raise SystemExit("cache_evidence: the build says nothing: " + refusal)
    graph, outputs = _graph(bazel, ws, a.target, a.scope)
    unreached = not_reached(graph_actions(graph, a.scope, a.target, outputs), spawns)
    if not a.keep:
        _rmtree(work)
    for line in summary_lines(counts, spawns, unreached):
        print(line)
    return 0 if counts["miss"] == 0 and not unreached else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("capture", help="ask the remote cache for every action")
    c.add_argument("target")
    c.add_argument("--scope", default="//test/", help="label prefix to itemize")
    c.add_argument("--bazel", default="bazelisk")
    c.add_argument("--keep", action="store_true", help="keep the output base and log")
    a = p.parse_args(argv)
    if a.cmd == "capture":
        return cmd_capture(a)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
