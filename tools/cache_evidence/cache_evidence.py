"""Key evidence for "why is this target not a remote cache hit here?".

Two machines share a remote cache and one of them rebuilds what the other
already built. Bazel can say which actions it ran and with what inputs,
but only for actions that were not local action-cache hits, and its logs
run to gigabytes. This keeps what it takes to name the first action whose
cache key differs between the machines, in a text file of kilobytes that
can be committed next to the design and diffed:

  - what shapes every key: Bazel version, commit and tree (the tree hash
    outlives a rebase, the commit hash does not), the rc options (values
    that name private infrastructure replaced by <redacted>), the host facts
    known to leak into inputs;
  - every tool the in-scope actions run, as one digest per tool;
  - every source file of this workspace an in-scope action reads, with its
    digest, so a differing design digest is traced to the file that moved;
  - one line per in-scope action: its cache key, whether it was a remote
    hit or a miss, and separate digests of its arguments, environment,
    tools, external sources and design inputs, so a differing key says
    which of the five moved.

`capture` runs the build in a fresh output base, so nothing is hidden by
the local action cache, and never lets an action execute: a remote cache
miss is spawned sandboxed and killed the moment it appears, so it fails in
a second, logged with its inputs, and `--keep_going` carries the build on
to every other action whose inputs exist. Remote hits never execute and
are unaffected; the strategy is not part of any cache key. Actions behind
a miss cannot be keyed, since their inputs were never produced; they are
listed as `not_reached` so their absence is never mistaken for a hit. An
action so short that it finished before it could be killed (writing a
variables file) is logged as `ran`: not a hit, and its result stays local
since uploading is off. A capture is therefore safe on a machine that only
consumes the cache: it downloads the inputs of each miss and computes
nothing that takes longer than a blink.

`summarize` turns an existing --execution_log_compact_file into the same
evidence. `diff` compares two evidence files and names the first action
that differs and why.
"""

import argparse
import datetime
import hashlib
import io
import os
import platform
import re
import shlex
import shutil
import signal
import json
import stat
import subprocess
import sys
import threading

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


def _digest_hash(buf):
    for num, val in _fields(buf):
        if num == 1:
            return val.decode()
    return ""


def _file(buf):
    path, digest = "", ""
    for num, val in _fields(buf):
        if num == 1:
            path = val.decode()
        elif num == 2:
            digest = _digest_hash(val)
    return path, digest


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


def _h(lines):
    m = hashlib.sha256()
    for line in lines:
        m.update(line.encode())
        m.update(b"\n")
    return m.hexdigest()[:12]


class Log(object):
    """The entries of one compact execution log, resolved on demand."""

    def __init__(self, data):
        self.entries = {}
        self.spawns = []
        for msg in _messages(data):
            eid, kind, body = 0, None, None
            for num, val in _fields(msg):
                if num == 1:
                    eid = val
                elif num >= 2:
                    kind, body = num, val
            if kind == _SPAWN:
                self.spawns.append(body)
            elif kind is not None:
                self.entries[eid] = (kind, body)
        self._sets = {}
        self._leaf = {}

    def path(self, eid):
        kind, body = self.entries[eid]
        for num, val in _fields(body):
            if num == 1:
                return val.decode()
        return ""

    def input_set(self, sid):
        """Leaf entry ids (files, directories, symlinks, runfiles trees)."""
        if not sid:
            return frozenset()
        if sid in self._sets:
            return self._sets[sid]
        leaves = set()
        kind, body = self.entries[sid]
        for num, val in _fields(body):
            if num == 5:
                leaves.update(_packed_uints(val))
            elif num == 4:
                for t in _packed_uints(val):
                    leaves |= self.input_set(t)
        result = frozenset(leaves)
        self._sets[sid] = result
        return result

    def _symlink_set(self, sid):
        entries = {}
        if not sid:
            return entries
        kind, body = self.entries[sid]
        for num, val in _fields(body):
            if num == 1:
                name, target = "", 0
                for n2, v2 in _fields(val):
                    if n2 == 1:
                        name = v2.decode()
                    elif n2 == 2:
                        target = v2
                entries[name] = target
            elif num == 2:
                for t in _packed_uints(val):
                    for name, target in self._symlink_set(t).items():
                        entries.setdefault(name, target)
        return entries

    def leaf(self, eid):
        """(path, digest) of a leaf; a tree or runfiles tree hashes whole."""
        if eid in self._leaf:
            return self._leaf[eid]
        kind, body = self.entries[eid]
        if kind == _FILE:
            result = _file(body)
        elif kind == _DIR:
            path, files = "", []
            for num, val in _fields(body):
                if num == 1:
                    path = val.decode()
                elif num == 2:
                    files.append("%s %s" % _file(val))
            result = (path, _h(sorted(files)))
        elif kind == _SYMLINK:
            path, target = "", ""
            for num, val in _fields(body):
                if num == 1:
                    path = val.decode()
                elif num == 2:
                    target = val.decode()
            result = (path, "symlink:" + target)
        elif kind == _RUNFILES:
            path, lines = "", []
            for num, val in _fields(body):
                if num == 1:
                    path = val.decode()
                elif num == 2:
                    lines += sorted("%s %s" % self.leaf(i) for i in self.input_set(val))
                elif num in (3, 4):
                    tag = "symlink" if num == 3 else "root_symlink"
                    for name, target in sorted(self._symlink_set(val).items()):
                        lines.append("%s %s %s" % (tag, name, self.leaf(target)[1]))
                elif num == 5:
                    lines.append("empty " + val.decode())
                elif num == 6:
                    lines.append("repo_mapping %s" % _file(val)[1])
            result = (path, _h(lines))
        else:
            result = ("?%d" % kind, "")
        self._leaf[eid] = result
        return result


# ---------------------------------------------------------------------------
# Classifying inputs. Every input of an in-scope action is a tool (built in
# an exec configuration, or a runfiles tree), an external source (a
# repository's own file), or a design input (built for the target, or a
# file of this workspace).


def _short(path):
    """bazel-out/k8-fastbuild/bin/x -> k8-fastbuild:x"""
    m = re.match(r"bazel-out/([^/]+)/bin/(.*)", path)
    return "%s:%s" % m.groups() if m else path


def input_class(path, is_runfiles):
    if is_runfiles or re.match(r"bazel-out/[^/]*-exec[^/]*/", path):
        return "tools"
    if path.startswith("external/"):
        return "sources"
    return "design"


def tool_group(path, is_runfiles):
    if is_runfiles:
        return _short(path)
    m = re.match(r"(bazel-out/[^/]+/bin/external/[^/]+)/", path)
    if m:
        return _short(m.group(1))
    m = re.match(r"(bazel-out/[^/]+/bin/(?:[^/]+/){0,2}[^/]+)", path)
    return _short(m.group(1) if m else path)


def _spawn_fields(buf):
    s = {
        "args": [],
        "env": [],
        "outputs": [],
        "input_set": 0,
        "label": "",
        "mnemonic": "",
        "exit": 0,
        "status": "",
        "runner": "",
        "cache_hit": False,
        "digest": "",
    }
    for num, val in _fields(buf):
        if num == 1:
            s["args"].append(val.decode())
        elif num == 2:
            name, value = "", ""
            for n2, v2 in _fields(val):
                if n2 == 1:
                    name = v2.decode()
                elif n2 == 2:
                    value = v2.decode()
            s["env"].append("%s=%s" % (name, value))
        elif num == 4:
            s["input_set"] = val
        elif num == 6:
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
        elif num == 11:
            s["runner"] = val.decode()
        elif num == 12:
            s["cache_hit"] = bool(val)
        elif num == 16:
            s["digest"] = _digest_hash(val)
    return s


def summarize_log(data, scope):
    """The evidence lines a compact log supports, for labels under scope."""
    log = Log(data)
    counts = {"spawns": 0, "hit": 0, "ran": 0, "miss": 0, "outside": []}
    tools = {}
    lines = []
    inputs = set()
    for buf in log.spawns:
        s = _spawn_fields(buf)
        counts["spawns"] += 1
        if s["cache_hit"]:
            status = "hit"
        elif s["exit"] != 0 or s["status"]:
            status = "miss"
        else:
            status = "ran"
        counts[status] += 1
        outs = []
        for kind, val in s["outputs"]:
            outs.append(log.path(val) if kind == "id" else val)
        if not s["label"].startswith(scope):
            if status != "hit":
                counts["outside"].append(
                    "%s %s %s (outside --scope)"
                    % (
                        status,
                        s["mnemonic"] or "-",
                        _short(sorted(outs)[0]) if outs else s["label"],
                    )
                )
            continue
        classes = {"tools": [], "sources": [], "design": []}
        for eid in log.input_set(s["input_set"]):
            is_runfiles = log.entries[eid][0] == _RUNFILES
            path, digest = log.leaf(eid)
            cls = input_class(path, is_runfiles)
            classes[cls].append("%s %s" % (path, digest))
            if cls == "design" and not path.startswith("bazel-out/"):
                inputs.add("input %s %s" % (digest[:12], path))
            if cls == "tools":
                tools.setdefault(tool_group(path, is_runfiles), set()).add(
                    "%s %s" % (path, digest)
                )
        lines.append(
            "spawn %s %s %s %s args=%s env=%s tools=%s sources=%s design=%s"
            % (
                s["digest"][:12] or "-" * 12,
                status,
                s["mnemonic"] or "-",
                _short(sorted(outs)[0]) if outs else s["label"],
                _h(s["args"]),
                _h(sorted(s["env"])),
                _h(sorted(classes["tools"])),
                _h(sorted(classes["sources"])),
                _h(sorted(classes["design"])),
            )
        )
    tool_lines = [
        "tool %s %d %s" % (_h(sorted(members)), len(members), group)
        for group, members in sorted(tools.items())
    ]
    return counts, tool_lines, lines, sorted(inputs)


def spawn_outputs(spawn_lines):
    """The first-output names the spawn lines are keyed by."""
    return {line.split(" ")[4] for line in spawn_lines}


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


def not_reached(graph, spawn_lines):
    """The in-scope actions of the graph the log has no spawn for."""
    logged = spawn_outputs(spawn_lines)
    return [
        "not_reached %s %s" % (mnemonic, out)
        for mnemonic, out in sorted(graph, key=lambda x: x[1])
        if out not in logged
    ]


# ---------------------------------------------------------------------------
# What shapes every key besides the inputs: options and host facts.

# Values of these options name private infrastructure (hosts, headers,
# credentials). They are dropped, not hashed: a short unsalted hash of a
# guessable hostname confirms the guess. Machines comparing cache hits
# share the cache by definition, so the value tells the diff nothing.
_PRIVATE = re.compile(
    r"remote|cache|header|credential|downloader|bes_|auth|proxy|google|netrc",
    re.I,
)


# Remote options whose value is a switch, not an address: whether a machine
# uploads what it builds is exactly what a later miss needs to know.
_PUBLIC_SWITCHES = {
    "--remote_upload_local_results",
    "--remote_cache_compression",
    "--remote_accept_cached",
    "--remote_local_fallback",
}
_SWITCH = re.compile(r"^(true|false|yes|no|0|1)$", re.I)


# Options whose value is NAME=VALUE for an environment: the name says which
# variable a machine sets, the value can name an account or a path, so the
# name stays and the value goes.
_ENV_OPTIONS = ("--repo_env", "--action_env", "--host_action_env", "--test_env")


def redact_option(opt):
    m = re.match(r"(--[\w@/:.+-]+)=(.*)", opt, re.S)
    if not m:
        return opt
    name, value = m.groups()
    if name in _ENV_OPTIONS and "=" in value:
        return "%s=%s=<redacted>" % (name, value.split("=", 1)[0])
    if name in _PUBLIC_SWITCHES and _SWITCH.match(value):
        return opt
    if (
        _PRIVATE.search(name)
        or re.search(r"(^|[=:,])/(home|Users|root)/", value)
        or re.search(r"@[\w-]+\.[a-z]{2,}\b", value, re.I)
    ):
        return "%s=<redacted>" % name
    return opt


# Anything that still looks like an address or a home directory after
# redaction stops the write rather than being published.
_LEAK = re.compile(r"://|(^|[\s=:,])/(home|Users|root)/|@[\w-]+\.[a-z]{2,}\b", re.I)


def check_public(lines):
    for line in lines:
        if _LEAK.search(line):
            raise ValueError("refusing to write evidence line: %r" % line)


def rc_options(announce_rc_text):
    """The options --announce_rc reports, each redacted, sorted unique."""
    opts = set()
    for line in announce_rc_text.splitlines():
        m = re.match(r"\s*(?:Inherited )?'[\w:-]+' options: (.*)", line)
        if not m:
            continue
        try:
            words = shlex.split(m.group(1))
        except ValueError:
            words = m.group(1).split()
        # `--cxxopt -std=c++20` is one option in two words.
        i = 0
        while i < len(words):
            w = words[i]
            i += 1
            if not w.startswith("--"):
                continue
            if "=" not in w and i < len(words) and not words[i].startswith("--"):
                w = "%s=%s" % (w, words[i])
                i += 1
            opts.add(redact_option(w))
    return sorted(opts)


def terminfo_digest(root="/usr/share/terminfo"):
    """@ncurses//:local_terminfo copies the host's terminfo into the graph.

    Harmless for the cache today (ncurses' fallback.c is built with no
    fallback terminals, so its output is the same stub on every host), but
    it is the one input known to come from the host, so it is witnessed.
    """
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        return "absent"
    lines = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                with open(p, "rb") as fh:
                    lines.append(
                        "%s %s"
                        % (
                            os.path.relpath(p, root),
                            hashlib.sha256(fh.read()).hexdigest(),
                        )
                    )
            except OSError:
                pass
    return "%s %d files" % (_h(sorted(lines)), len(lines))


def host_line():
    pretty = "unknown"
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    pretty = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    libc = " ".join(platform.libc_ver())
    return "%s; %s; %s" % (pretty, libc, platform.machine())


# ---------------------------------------------------------------------------
# Commands.


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


def write_evidence(
    out, header, counts, tool_lines, spawn_lines, unreached=(), input_lines=()
):
    lines = ["# Written by tools/cache_evidence; see its docstring."]
    lines += header
    lines.append(
        "spawns %d hit %d ran %d miss %d not_reached %d"
        % (
            counts["spawns"],
            counts["hit"],
            counts["ran"],
            counts["miss"],
            len(unreached),
        )
    )
    lines += tool_lines
    lines += list(input_lines)
    lines += spawn_lines
    lines += list(unreached)
    check_public(lines)
    text = "\n".join(lines) + "\n"
    if out == "-":
        sys.stdout.write(text)
    else:
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out, "w") as fh:
            fh.write(text)


def _git(workspace, *args):
    try:
        return subprocess.check_output(
            ("git", "-C", workspace) + args, universal_newlines=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _package(target):
    """//a/b:c -> a/b, the directory whose tree hash is the design's."""
    m = re.match(r"(?:@@?[^/]*)?//([^:]*)", target)
    return m.group(1) if m else "."


def in_history(workspace, commit):
    """Whether commit is an ancestor of the workspace's HEAD: 'yes', 'no',
    or 'unknown' when git has never heard of it."""
    if not workspace or not re.match(r"^[0-9a-f]{7,40}$", commit or ""):
        return "unknown"
    with open(os.devnull, "w") as null:
        rc = subprocess.call(
            ["git", "-C", workspace, "merge-base", "--is-ancestor", commit, "HEAD"],
            stdout=null,
            stderr=null,
        )
    return {0: "yes", 1: "no"}.get(rc, "unknown")


def _rmtree(path):
    def onerror(func, p, _):
        os.chmod(os.path.dirname(p), stat.S_IRWXU)
        if os.path.isdir(p):
            os.chmod(p, stat.S_IRWXU)
        func(p)

    shutil.rmtree(path, onerror=onerror)


def sandboxed_pids(root, proc="/proc", self_pid=None):
    """Processes running inside a sandbox under root: their working
    directory is there (an action's own process, or an orphan it left),
    or their command line names it (Bazel's wrapper around the action)."""
    self_pid = os.getpid() if self_pid is None else self_pid
    found = []
    for name in os.listdir(proc):
        if not name.isdigit() or int(name) == self_pid:
            continue
        try:
            with open(os.path.join(proc, name, "cmdline"), "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
            cwd = os.readlink(os.path.join(proc, name, "cwd"))
        except OSError:
            continue
        if root in cmd or cwd.startswith(root):
            found.append(int(name))
    return found


class Killer(threading.Thread):
    """Kills every process a sandboxed action starts, for as long as the
    build runs. A remote cache hit never starts one; a miss dies before it
    computes anything, and Bazel logs it, with its inputs, as failed."""

    def __init__(self, output_base, period=0.05):
        threading.Thread.__init__(self)
        self.daemon = True
        self.root = os.path.join(output_base, "sandbox") + os.sep
        self.period = period
        self.killed = set()
        self.done = threading.Event()

    def run(self):
        while not self.done.is_set():
            for pid in sandboxed_pids(self.root):
                try:
                    os.kill(pid, signal.SIGKILL)
                    self.killed.add(pid)
                except OSError:
                    pass
            self.done.wait(self.period)

    def stop(self):
        self.done.set()
        self.join()


def capture_refusal(counts, build_text):
    """Why a capture must not be written, or None. A build that stopped
    before its first action -- a flag Bazel refused, a failed fetch --
    logs no spawns, and evidence of no spawns says nothing about the cache."""
    if counts["spawns"] > 0:
        return None
    errors = [l for l in build_text.splitlines() if l.startswith("ERROR:")]
    return errors[0] if errors else "the build logged no actions"


def summary_lines(counts, spawn_lines, unreached):
    """What a capture found, for the terminal: the counts, every miss and
    every action left unreached behind one."""
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
    for line in spawn_lines:
        f = line.split(" ")
        if f[2] != "hit":
            out.append("%s %s %s" % (f[2], f[3], f[4]))
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
    rc = subprocess.run(
        bazel + ["build", "--announce_rc", "--nobuild", a.target],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    ).stdout
    version = subprocess.run(
        bazel + ["version"],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        universal_newlines=True,
    ).stdout
    release = re.search(r"Build label: (\S+)", version)
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
    header = [
        "target %s" % a.target,
        "bazel %s" % (release.group(1) if release else "unknown"),
        "commit %s dirty %d"
        % (
            _git(ws, "rev-parse", "HEAD"),
            1 if _git(ws, "status", "--porcelain", "--untracked-files=no") else 0,
        ),
        "tree %s" % _git(ws, "rev-parse", "HEAD^{tree}"),
        "design_tree %s" % _git(ws, "rev-parse", "HEAD:" + _package(a.target)),
        "host %s" % host_line(),
        "terminfo %s" % terminfo_digest(),
    ]
    header += ["option %s" % o for o in rc_options(rc)]
    counts, tool_lines, spawn_lines, input_lines = summarize_log(
        _decompress(log), a.scope
    )
    with open(os.path.join(work, "build.txt")) as fh:
        refusal = capture_refusal(counts, fh.read())
    if refusal:
        subprocess.run(bazel + ["shutdown"], cwd=ws)
        raise SystemExit("cache_evidence: refusing to write evidence: " + refusal)
    graph, outputs = _graph(bazel, ws, a.target, a.scope)
    unreached = not_reached(
        graph_actions(graph, a.scope, a.target, outputs), spawn_lines
    )
    if a.out == "-" or os.path.isabs(a.out):
        out = a.out
    else:
        out = os.path.join(ws, a.out)
    write_evidence(out, header, counts, tool_lines, spawn_lines, unreached, input_lines)
    if not a.keep:
        _rmtree(work)
    for line in summary_lines(counts, spawn_lines, unreached):
        sys.stderr.write("cache_evidence: %s\n" % line)
    if out != "-":
        sys.stderr.write("cache_evidence: wrote %s\n" % out)
    return 0 if counts["miss"] == 0 and not unreached else 1


def cmd_summarize(a):
    counts, tool_lines, spawn_lines, input_lines = summarize_log(
        _decompress(a.log), a.scope
    )
    write_evidence(a.out, [], counts, tool_lines, spawn_lines, (), input_lines)


def _read(path):
    header, tools, spawns = {}, {}, []
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            kind, _, rest = line.partition(" ")
            if kind == "tool":
                digest, n, group = rest.split(" ", 2)
                tools[group] = digest
            elif kind == "spawn":
                f = rest.split(" ")
                spawns.append(
                    {
                        "key": f[0],
                        "status": f[1],
                        "mnemonic": f[2],
                        "out": f[3],
                        "parts": dict(p.split("=", 1) for p in f[4:]),
                    }
                )
            elif kind == "option":
                header.setdefault("option", set()).add(rest)
            elif kind == "not_reached":
                header.setdefault("not_reached", []).append(rest)
            elif kind == "input":
                digest, _, path = rest.partition(" ")
                header.setdefault("input", {})[path] = digest
            else:
                header[kind] = rest
    return header, tools, spawns


def diff(a_path, b_path, workspace=None):
    """Lines naming what differs, most fundamental first."""
    ha, ta, sa = _read(a_path)
    hb, tb, sb = _read(b_path)
    out = []
    for k in ("target", "bazel", "commit", "tree", "design_tree", "host", "terminfo"):
        if ha.get(k) != hb.get(k):
            line = "%s: %s | %s" % (k, ha.get(k), hb.get(k))
            if k == "commit" and workspace:
                for side, h in (("A", ha), ("B", hb)):
                    where = in_history(workspace, (h.get("commit") or "").split(" ")[0])
                    if where == "no":
                        line += " (%s not in this history)" % side
                    elif where == "unknown":
                        line += " (%s unknown to this repository)" % side
            out.append(line)
    if ha.get("tree") and ha.get("tree") == hb.get("tree"):
        out.append("same tree: the sources are identical, look at tools and options")
    oa, ob = ha.get("option", set()), hb.get("option", set())
    for o in sorted(oa - ob):
        out.append("option only in A: %s" % o)
    for o in sorted(ob - oa):
        out.append("option only in B: %s" % o)
    for g in sorted(set(ta) | set(tb)):
        if ta.get(g) != tb.get(g):
            out.append("tool %s: %s | %s" % (g, ta.get(g, "-"), tb.get(g, "-")))
    ia, ib = ha.get("input", {}), hb.get("input", {})
    moved = []
    if ia and ib:
        for path in sorted(set(ia) | set(ib)):
            if ia.get(path) != ib.get(path):
                moved.append(path)
                out.append(
                    "input %s: %s | %s" % (path, ia.get(path, "-"), ib.get(path, "-"))
                )
    elif ia or ib:
        out.append("input lines only in %s: an older capture" % ("A" if ia else "B"))
    by_out = {s["out"]: s for s in sb}
    first = None
    for s in sa:
        t = by_out.get(s["out"])
        if t is None or s["key"] == t["key"]:
            continue
        parts = [k for k in s["parts"] if s["parts"][k] != t["parts"].get(k)]
        line = "spawn %s %s: key %s %s | %s %s; differs in %s" % (
            s["mnemonic"],
            s["out"],
            s["key"],
            s["status"],
            t["key"],
            t["status"],
            ", ".join(parts) or "nothing summarized (key only)",
        )
        if "design" in parts and moved and first is None:
            line += "; source files moved: %s" % ", ".join(moved[:5])
            if len(moved) > 5:
                line += " and %d more" % (len(moved) - 5)
        out.append(line)
        if first is None:
            first = line
    only_a = [s["out"] for s in sa if s["out"] not in by_out]
    if only_a:
        out.append("%d in-scope actions logged only in A" % len(only_a))
    names_a = {s["out"] for s in sa}
    only_b = [s["out"] for s in sb if s["out"] not in names_a]
    if only_b:
        out.append("%d in-scope actions logged only in B" % len(only_b))
    if first:
        out.append("first differing action: " + first)
    return out


def cmd_diff(a):
    lines = diff(a.a, a.b, os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd()))
    for line in lines:
        print(line)
    if not lines:
        print("no difference in the evidence")
    return 1 if lines else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("capture", help="build in a fresh output base, write evidence")
    c.add_argument("target")
    c.add_argument(
        "--out",
        required=True,
        help="evidence file, workspace-relative; - prints it and keeps nothing",
    )
    c.add_argument("--scope", default="//test/", help="label prefix to itemize")
    c.add_argument("--bazel", default="bazelisk")
    c.add_argument("--keep", action="store_true", help="keep the output base and log")
    s = sub.add_parser("summarize", help="evidence from an existing compact log")
    s.add_argument("log")
    s.add_argument("--out", default="-")
    s.add_argument("--scope", default="//test/")
    d = sub.add_parser("diff", help="compare two evidence files")
    d.add_argument("a")
    d.add_argument("b")
    a = p.parse_args(argv)
    if a.cmd == "capture":
        return cmd_capture(a)
    if a.cmd == "summarize":
        return cmd_summarize(a)
    if a.cmd == "diff":
        return cmd_diff(a)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
