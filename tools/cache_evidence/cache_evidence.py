"""Key evidence for "why is this target not a remote cache hit here?".

Two machines share a remote cache and one of them rebuilds what the other
already built. Bazel can say which actions it ran and with what inputs,
but only for actions that were not local action-cache hits, and its logs
run to gigabytes. This keeps what it takes to name the first action whose
cache key differs between the machines, in a text file of kilobytes that
can be committed next to the design and diffed:

  - what shapes every key: Bazel version, commit, the rc options (values
    that name private infrastructure replaced by <redacted>), the host facts
    known to leak into inputs;
  - every tool the in-scope actions run, as one digest per tool;
  - one line per in-scope action: its cache key, whether it was a remote
    hit or a miss, and separate digests of its arguments, environment,
    tools, external sources and design inputs, so a differing key says
    which of the five moved.

`capture` runs the build in a fresh output base, so nothing is hidden by
the local action cache, and with `/usr` and `/bin` blocked in the sandbox,
so a remote cache miss fails in a second, and is logged with its inputs,
instead of executing for hours. Remote hits never execute and are
unaffected; sandbox options are not part of any cache key.

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
import stat
import subprocess
import sys

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
    counts = {"spawns": 0, "hit": 0, "ran": 0, "miss": 0}
    tools = {}
    lines = []
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
        if not s["label"].startswith(scope):
            continue
        outs = []
        for kind, val in s["outputs"]:
            outs.append(log.path(val) if kind == "id" else val)
        classes = {"tools": [], "sources": [], "design": []}
        for eid in log.input_set(s["input_set"]):
            is_runfiles = log.entries[eid][0] == _RUNFILES
            path, digest = log.leaf(eid)
            cls = input_class(path, is_runfiles)
            classes[cls].append("%s %s" % (path, digest))
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
    return counts, tool_lines, lines


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


def redact_option(opt):
    m = re.match(r"(--[\w@/:.+-]+)=(.*)", opt, re.S)
    if not m:
        return opt
    name, value = m.groups()
    if _PRIVATE.search(name) or re.search(r"(^|[=:,])/(home|Users|root)/", value):
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


def write_evidence(out, header, counts, tool_lines, spawn_lines):
    lines = ["# Written by tools/cache_evidence; see its docstring."]
    lines += header
    lines.append(
        "spawns %d hit %d ran %d miss %d"
        % (counts["spawns"], counts["hit"], counts["ran"], counts["miss"])
    )
    lines += tool_lines
    lines += spawn_lines
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


def _rmtree(path):
    def onerror(func, p, _):
        os.chmod(os.path.dirname(p), stat.S_IRWXU)
        if os.path.isdir(p):
            os.chmod(p, stat.S_IRWXU)
        func(p)

    shutil.rmtree(path, onerror=onerror)


# The progress line of an action the remote cache did not have.
_LOCAL = re.compile(r"remote-cache, (linux-sandbox|processwrapper-sandbox|local)")


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
    ]
    if not a.allow_local:
        # A miss fails at once, logged with its inputs, instead of running.
        build += [
            "--spawn_strategy=linux-sandbox",
            "--sandbox_block_path=/usr",
            "--sandbox_block_path=/bin",
        ]
    sys.stderr.write("cache_evidence: %s\n" % " ".join(build))
    with open(os.path.join(work, "build.txt"), "w") as out:
        proc = subprocess.Popen(
            build,
            cwd=ws,
            stdout=out,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        for line in proc.stderr:
            out.write(line)
            if a.allow_local and _LOCAL.search(line):
                # Allowed to run, but the first local execution is the
                # evidence; everything after it is hours of nothing new.
                proc.send_signal(signal.SIGINT)
        proc.wait()
    subprocess.run(bazel + ["shutdown"], cwd=ws)
    header = [
        "target %s" % a.target,
        "bazel %s" % (release.group(1) if release else "unknown"),
        "commit %s dirty %d"
        % (
            _git(ws, "rev-parse", "HEAD"),
            1 if _git(ws, "status", "--porcelain", "--untracked-files=no") else 0,
        ),
        "host %s" % host_line(),
        "terminfo %s" % terminfo_digest(),
    ]
    header += ["option %s" % o for o in rc_options(rc)]
    counts, tool_lines, spawn_lines = summarize_log(_decompress(log), a.scope)
    out = a.out if os.path.isabs(a.out) else os.path.join(ws, a.out)
    write_evidence(out, header, counts, tool_lines, spawn_lines)
    if not a.keep:
        _rmtree(work)
    sys.stderr.write("cache_evidence: wrote %s\n" % out)


def cmd_summarize(a):
    counts, tool_lines, spawn_lines = summarize_log(_decompress(a.log), a.scope)
    write_evidence(a.out, [], counts, tool_lines, spawn_lines)


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
            else:
                header[kind] = rest
    return header, tools, spawns


def diff(a_path, b_path):
    """Lines naming what differs, most fundamental first."""
    ha, ta, sa = _read(a_path)
    hb, tb, sb = _read(b_path)
    out = []
    for k in ("target", "bazel", "commit", "host", "terminfo"):
        if ha.get(k) != hb.get(k):
            out.append("%s: %s | %s" % (k, ha.get(k), hb.get(k)))
    oa, ob = ha.get("option", set()), hb.get("option", set())
    for o in sorted(oa - ob):
        out.append("option only in A: %s" % o)
    for o in sorted(ob - oa):
        out.append("option only in B: %s" % o)
    for g in sorted(set(ta) | set(tb)):
        if ta.get(g) != tb.get(g):
            out.append("tool %s: %s | %s" % (g, ta.get(g, "-"), tb.get(g, "-")))
    by_out = {s["out"]: s for s in sb}
    first = None
    for s in sa:
        t = by_out.get(s["out"])
        if t is None or s["key"] == t["key"]:
            continue
        moved = [k for k in s["parts"] if s["parts"][k] != t["parts"].get(k)]
        line = "spawn %s %s: key %s %s | %s %s; differs in %s" % (
            s["mnemonic"],
            s["out"],
            s["key"],
            s["status"],
            t["key"],
            t["status"],
            ", ".join(moved) or "nothing summarized (key only)",
        )
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
    lines = diff(a.a, a.b)
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
    c.add_argument("--out", required=True, help="evidence file, workspace-relative")
    c.add_argument("--scope", default="//test/", help="label prefix to itemize")
    c.add_argument("--bazel", default="bazelisk")
    c.add_argument(
        "--allow_local",
        action="store_true",
        help="let a miss execute; stop the build at the first one",
    )
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
