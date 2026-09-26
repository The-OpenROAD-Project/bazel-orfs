"""cache_evidence on hand-encoded execution logs."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import zstandard

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cache_evidence as ce  # noqa: E402


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _len(num, payload):
    if isinstance(payload, str):
        payload = payload.encode()
    return _varint(num << 3 | 2) + _varint(len(payload)) + payload


def _int(num, value):
    return _varint(num << 3) + _varint(value)


def _entry(eid, kind, body):
    msg = _int(1, eid) + _len(kind, body)
    return _varint(len(msg)) + msg


def _file(path, digest):
    return _len(1, path) + _len(2, _len(1, digest))


def _spawn(label, outputs_id, input_set, digest, hit=True, exit_code=0, env=""):
    body = _len(1, "bash") + _len(1, "-c") + _len(1, "make")
    if env:
        body += _len(2, _len(1, "V") + _len(2, env))
    body += _int(4, input_set)
    body += _len(6, _int(5, outputs_id))
    body += _len(7, label) + _len(8, "Action")
    if exit_code:
        body += _int(9, exit_code)
    body += _len(11, "remote cache hit" if hit else "linux-sandbox")
    if hit:
        body += _int(12, 1)
    body += _len(16, _len(1, digest))
    return body


def _log(tool_digest="aa", miss=False, sdc_digest="cc"):
    """A tool, a flow script, a design input; two actions, one downstream."""
    entries = [
        _entry(
            1,
            ce._FILE,
            _file("bazel-out/k8-opt-exec/bin/external/yosys+/yosys", tool_digest),
        ),
        _entry(2, ce._FILE, _file("external/orfs/flow/scripts/synth.tcl", "bb")),
        _entry(3, ce._FILE, _file("test/d/constraints.sdc", sdc_digest)),
        _entry(4, ce._INPUT_SET, _len(5, _varint(1) + _varint(2))),
        _entry(5, ce._INPUT_SET, _len(5, _varint(3)) + _len(4, _varint(4))),
        _entry(6, ce._FILE, _file("bazel-out/k8-fastbuild/bin/test/d/1_synth.v", "dd")),
        _entry(
            7,
            ce._SPAWN,
            _spawn("//test/d:synth", 6, 5, "key1" + tool_digest + sdc_digest),
        ),
        _entry(8, ce._INPUT_SET, _len(5, _varint(6)) + _len(4, _varint(4))),
        _entry(
            9,
            ce._FILE,
            _file("bazel-out/k8-fastbuild/bin/test/d/2_floorplan.odb", "ee"),
        ),
        _entry(
            10,
            ce._SPAWN,
            _spawn(
                "//test/d:floorplan",
                9,
                8,
                "key2" + tool_digest,
                hit=not miss,
                exit_code=1 if miss else 0,
            ),
        ),
        _entry(11, ce._SPAWN, _spawn("@yosys//:yosys", 1, 0, "key3")),
    ]
    return b"".join(entries)


class SummarizeTest(unittest.TestCase):
    def test_classes_and_scope(self):
        counts, tools, spawns, _ = ce.summarize_log(_log(), "//test/")
        self.assertEqual(
            counts, {"spawns": 3, "hit": 3, "ran": 0, "miss": 0, "outside": []}
        )
        # The out-of-scope tool build is counted, not itemized.
        self.assertEqual(len(spawns), 2)
        self.assertIn("hit Action k8-fastbuild:test/d/1_synth.v", spawns[0])
        self.assertEqual(len(tools), 1)
        self.assertIn("k8-opt-exec:external/yosys+", tools[0])
        # No action here has an environment; the empty hash is stable.
        self.assertIn("env=" + ce._h([]), spawns[0])

    def test_source_inputs_listed(self):
        _, _, _, inputs = ce.summarize_log(_log(), "//test/")
        # the workspace file, not the generated netlist nor the external script
        self.assertEqual(inputs, ["input cc test/d/constraints.sdc"])

    def test_miss(self):
        counts, _, spawns, _ = ce.summarize_log(_log(miss=True), "//test/")
        self.assertEqual(counts["miss"], 1)
        self.assertIn(" miss Action k8-fastbuild:test/d/2_floorplan.odb", spawns[1])

    def test_truncated_log(self):
        data = _log()
        counts, _, spawns, _ = ce.summarize_log(data[:-5], "//test/")
        self.assertEqual(counts["spawns"], 2)

    def test_zstd_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.zst")
            with open(path, "wb") as fh:
                fh.write(zstandard.ZstdCompressor().compress(_log()))
            self.assertEqual(ce._decompress(path), _log())


class DiffTest(unittest.TestCase):
    def _write(self, d, name, header, log):
        path = os.path.join(d, name)
        counts, tools, spawns, inputs = ce.summarize_log(log, "//test/")
        ce.write_evidence(path, header, counts, tools, spawns, (), inputs)
        return path

    def test_names_the_tool_and_first_action(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._write(d, "a.txt", ["bazel 9.1.1"], _log("aa"))
            b = self._write(d, "b.txt", ["bazel 9.1.1"], _log("zz"))
            lines = ce.diff(a, b)
        self.assertTrue(
            any(l.startswith("tool k8-opt-exec:external/yosys+") for l in lines)
        )
        self.assertIn("differs in tools", lines[-1])
        self.assertIn("1_synth.v", lines[-1])

    def test_same(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._write(d, "a.txt", ["bazel 9.1.1"], _log())
            b = self._write(d, "b.txt", ["bazel 9.1.1"], _log())
            self.assertEqual(ce.diff(a, b), [])

    def test_header(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._write(d, "a.txt", ["bazel 9.1.1", "option --x=1"], _log())
            b = self._write(d, "b.txt", ["bazel 9.0.0", "option --x=2"], _log())
            lines = ce.diff(a, b)
        self.assertIn("bazel: 9.1.1 | 9.0.0", lines)
        self.assertIn("option only in A: --x=1", lines)

    def test_source_file_named(self):
        # the same log, the design's constraints file with another digest
        with tempfile.TemporaryDirectory() as d:
            a = self._write(d, "a.txt", ["tree t1"], _log())
            b = self._write(d, "b.txt", ["tree t2"], _log(sdc_digest="c2"))
            lines = ce.diff(a, b)
        self.assertIn("tree: t1 | t2", lines)
        self.assertIn("input test/d/constraints.sdc: cc | c2", lines)
        self.assertIn(
            "differs in design; source files moved: test/d/constraints.sdc", lines[-1]
        )
        self.assertIn("1_synth.v", lines[-1])

    def test_same_tree_said(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._write(d, "a.txt", ["tree t1", "commit c1 dirty 0"], _log("aa"))
            b = self._write(d, "b.txt", ["tree t1", "commit c2 dirty 0"], _log("zz"))
            lines = ce.diff(a, b)
        self.assertEqual(lines[0], "commit: c1 dirty 0 | c2 dirty 0")
        self.assertTrue(lines[1].startswith("same tree:"))

    def test_commit_not_in_history(self):
        with tempfile.TemporaryDirectory() as d:
            ws = os.path.join(d, "ws")
            os.makedirs(ws)
            git = (
                lambda *a: subprocess.check_output(("git", "-C", ws) + a)
                .decode()
                .strip()
            )
            git("init", "-q")
            git(
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "one",
            )
            head = git("rev-parse", "HEAD")
            self.assertEqual(ce.in_history(ws, head), "yes")
            self.assertEqual(ce.in_history(ws, "0" * 40), "unknown")
            self.assertEqual(ce.in_history(None, head), "unknown")
            self.assertEqual(ce.in_history(ws, "not a hash"), "unknown")
            git(
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "two",
            )
            git("checkout", "-q", "-b", "side", head)
            git(
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "lost",
            )
            lost = git("rev-parse", "HEAD")
            git("checkout", "-q", "-")
            self.assertEqual(ce.in_history(ws, lost), "no")
            a = self._write(d, "a.txt", ["commit %s dirty 0" % lost], _log())
            b = self._write(d, "b.txt", ["commit %s dirty 0" % head], _log())
            lines = ce.diff(a, b, ws)
            self.assertTrue(lines[0].endswith("(A not in this history)"), lines[0])
            a = self._write(d, "a.txt", ["commit %s dirty 0" % ("0" * 40)], _log())
            lines = ce.diff(a, b, ws)
            self.assertTrue(
                lines[0].endswith("(A unknown to this repository)"), lines[0]
            )

    def test_old_capture_without_input_lines(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            counts, tools, spawns, _ = ce.summarize_log(_log(), "//test/")
            ce.write_evidence(a, [], counts, tools, spawns)
            b = self._write(d, "b.txt", [], _log(sdc_digest="c2"))
            lines = ce.diff(a, b)
        self.assertIn("input lines only in B: an older capture", lines)
        self.assertFalse(any(l.startswith("input test/") for l in lines))
        self.assertNotIn("source files moved", lines[-1])

    def test_package(self):
        self.assertEqual(ce._package("//test/d:synth"), "test/d")
        self.assertEqual(ce._package("@@repo//x/y:z"), "x/y")
        self.assertEqual(ce._package("//:top"), "")


class RedactTest(unittest.TestCase):
    def test_remote_switches_kept(self):
        # whether a machine uploads is what a later miss needs to know
        for opt in (
            "--remote_upload_local_results=true",
            "--remote_upload_local_results=false",
            "--remote_cache_compression=true",
            "--noremote_upload_local_results",
        ):
            self.assertEqual(ce.redact_option(opt), opt)
        # a switch whose value is not a switch is still an address
        self.assertEqual(
            ce.redact_option("--remote_upload_local_results=grpc://h:1"),
            "--remote_upload_local_results=<redacted>",
        )

    def test_private_values_dropped(self):
        # Not hashed: a hash of a guessable hostname confirms the guess.
        self.assertEqual(
            ce.redact_option("--remote_cache=grpc://cache.example:9092"),
            "--remote_cache=<redacted>",
        )
        self.assertEqual(
            ce.redact_option("--disk_cache_dir=/home/alice/c"),
            "--disk_cache_dir=<redacted>",
        )

    def test_separate_value(self):
        opts = ce.rc_options(
            "  'build' options: --cxxopt -std=c++20 "
            "--remote_header Authorization=secret --keep_going\n"
        )
        self.assertIn("--cxxopt=-std=c++20", opts)
        self.assertIn("--remote_header=<redacted>", opts)
        self.assertIn("--keep_going", opts)
        self.assertFalse(any("secret" in o for o in opts))

    def test_leak_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in (
                "option --x=grpc://cache.example:1",
                "option --y=/home/alice/z",
                "note someone@example.com",
            ):
                with self.assertRaises(ValueError):
                    ce.write_evidence(
                        os.path.join(d, "e.txt"),
                        [bad],
                        ce.summarize_log(b"", "//")[0],
                        [],
                        [],
                    )

    def test_plain_options_kept(self):
        self.assertEqual(ce.redact_option("--jobs=2"), "--jobs=2")
        self.assertEqual(ce.redact_option("--keep_going"), "--keep_going")

    def test_environment_values_and_addresses_redacted(self):
        # an environment's variable stays, its value goes
        self.assertEqual(
            ce.redact_option("--repo_env=CLOUDSDK_CORE_ACCOUNT=bot@corp.example.com"),
            "--repo_env=CLOUDSDK_CORE_ACCOUNT=<redacted>",
        )
        self.assertEqual(
            ce.redact_option("--action_env=PATH=/usr/bin"),
            "--action_env=PATH=<redacted>",
        )
        # any other value that names an address is dropped whole
        self.assertEqual(
            ce.redact_option("--some_flag=user@corp.example.com"),
            "--some_flag=<redacted>",
        )
        ce.check_public([ce.redact_option("--repo_env=A=b@corp.example.com")])

    def test_capture_refuses_a_build_with_no_actions(self):
        none = {"spawns": 0, "hit": 0, "ran": 0, "miss": 0}
        why = ce.capture_refusal(none, "INFO: x\nERROR: no such package 'y'\n")
        self.assertEqual(why, "ERROR: no such package 'y'")
        self.assertEqual(ce.capture_refusal(none, ""), "the build logged no actions")
        self.assertIsNone(ce.capture_refusal(dict(none, spawns=3, hit=3), "ERROR: x"))

    def test_announce_rc(self):
        text = (
            "INFO: Reading rc options for 'build' from /x/.bazelrc:\n"
            "  Inherited 'common' options: --lockfile_mode=off "
            "--remote_cache=grpc://h:1\n"
            "  'build' options: --jobs=2\n"
        )
        opts = ce.rc_options(text)
        self.assertIn("--jobs=2", opts)
        self.assertIn("--lockfile_mode=off", opts)
        self.assertFalse(any("grpc" in o for o in opts))


def _aquery(*actions):
    """aquery --output=jsonproto for actions given as (label, mnemonic, out)
    or (label, mnemonic, out, [input outs]): each input is another action's
    output, and reaches it through a depset of its own."""
    frags, fid = [], {}

    def frag(path):
        parent = None
        for i, part in enumerate(path.split("/")):
            key = "/".join(path.split("/")[: i + 1])
            if key not in fid:
                fid[key] = len(frags) + 1
                f = {"id": fid[key], "label": part}
                if parent is not None:
                    f["parentId"] = parent
                frags.append(f)
            parent = fid[key]
        return parent

    targets, tid, arts, aid, acts, depsets = [], {}, [], {}, [], []
    for spec in actions:
        label, mnemonic, out = spec[:3]
        if label not in tid:
            tid[label] = len(targets) + 1
            targets.append({"id": tid[label], "label": label})
        aid[out] = len(arts) + 1
        arts.append({"id": aid[out], "pathFragmentId": frag(out)})
        act = {"targetId": tid[label], "mnemonic": mnemonic, "outputIds": [aid[out]]}
        if len(spec) > 3 and spec[3]:
            # one depset holding the first input, nesting one for the rest
            ids = [aid[i] for i in spec[3]]
            inner = {"id": len(depsets) + 1, "directArtifactIds": ids[1:]}
            depsets.append(inner)
            outer = {
                "id": len(depsets) + 1,
                "directArtifactIds": ids[:1],
                "transitiveDepSetIds": [inner["id"]],
            }
            depsets.append(outer)
            act["inputDepSetIds"] = [outer["id"]]
        acts.append(act)
    return json.dumps(
        {
            "artifacts": arts,
            "actions": acts,
            "targets": targets,
            "pathFragments": frags,
            "depSetOfFiles": depsets,
        }
    )


class FrontierTest(unittest.TestCase):
    OUT = "bazel-out/k8-fastbuild/bin/test/d/"
    GRAPH = _aquery(
        ("//test/d:synth", "Action", OUT + "1_synth.v"),
        ("//test/d:synth", "FileWrite", OUT + "config.mk", [OUT + "1_synth.v"]),
        ("//test/d:synth", "Action", OUT + "1_synth.vars"),
        ("//test/d:floorplan", "Action", OUT + "2_floorplan.odb", [OUT + "1_synth.v"]),
        ("//test/d:place", "Action", OUT + "3_place.odb", [OUT + "2_floorplan.odb"]),
        (
            "//test/d:place_deps",
            "OrfsPackage",
            OUT + "place_deps.tar.gz",
            [OUT + "3_place.odb"],
        ),
        (
            "@yosys//:yosys",
            "CppLink",
            "bazel-out/k8-opt-exec/bin/external/yosys+/yosys",
        ),
    )

    def test_graph_actions_reach_only_what_the_target_needs(self):
        # place needs floorplan needs synth; not synth's vars file, not the
        # tarball that needs place
        self.assertEqual(
            ce.graph_actions(self.GRAPH, "//test/", "//test/d:place"),
            [
                ("Action", "k8-fastbuild:test/d/1_synth.v"),
                ("Action", "k8-fastbuild:test/d/2_floorplan.odb"),
                ("Action", "k8-fastbuild:test/d/3_place.odb"),
            ],
        )
        self.assertEqual(
            ce.graph_actions(self.GRAPH, "//test/", "@@//test/d:floorplan"),
            [
                ("Action", "k8-fastbuild:test/d/1_synth.v"),
                ("Action", "k8-fastbuild:test/d/2_floorplan.odb"),
            ],
        )
        self.assertEqual(ce._label("//test/d"), "//test/d:d")
        self.assertEqual(ce._label("@@//test/d:x"), "//test/d:x")
        # rooted at the default outputs, the target's own tarball is not needed
        self.assertEqual(
            ce.graph_actions(
                self.GRAPH, "//test/", "//test/d:place_deps", [self.OUT + "3_place.odb"]
            ),
            [
                ("Action", "k8-fastbuild:test/d/1_synth.v"),
                ("Action", "k8-fastbuild:test/d/2_floorplan.odb"),
                ("Action", "k8-fastbuild:test/d/3_place.odb"),
            ],
        )

    def test_graph_actions_skip_internal_and_out_of_scope(self):
        graph = ce.graph_actions(self.GRAPH, "//test/")
        self.assertEqual(
            graph,
            [
                ("Action", "k8-fastbuild:test/d/1_synth.v"),
                ("Action", "k8-fastbuild:test/d/1_synth.vars"),
                ("Action", "k8-fastbuild:test/d/2_floorplan.odb"),
                ("Action", "k8-fastbuild:test/d/3_place.odb"),
                ("OrfsPackage", "k8-fastbuild:test/d/place_deps.tar.gz"),
            ],
        )
        self.assertEqual(ce.graph_actions("", "//test/"), [])

    def test_not_reached_is_what_the_log_lacks(self):
        graph = ce.graph_actions(self.GRAPH, "//test/", "//test/d:place")
        counts, _, spawns, _ = ce.summarize_log(_log(miss=True), "//test/")
        unreached = ce.not_reached(graph, spawns)
        # synth hit, floorplan missed; place behind the miss was never keyed
        self.assertEqual(
            unreached, ["not_reached Action k8-fastbuild:test/d/3_place.odb"]
        )
        lines = ce.summary_lines(counts, spawns, unreached)
        self.assertEqual(lines[0], "spawns 3 hit 2 ran 0 miss 1 not_reached 1")
        self.assertEqual(lines[1], "miss Action k8-fastbuild:test/d/2_floorplan.odb")
        self.assertEqual(lines[2], unreached[0])
        self.assertNotIn("every action is a remote cache hit", lines)
        # a miss the scope does not itemize is still named
        counts, _, spawns, _ = ce.summarize_log(_log(miss=True), "//test/d:s")
        self.assertEqual(
            counts["outside"],
            ["miss Action k8-fastbuild:test/d/2_floorplan.odb (outside --scope)"],
        )
        self.assertIn(counts["outside"][0], ce.summary_lines(counts, spawns, []))

    def test_all_hits_say_so(self):
        graph = ce.graph_actions(self.GRAPH, "//test/", "//test/d:place")
        counts, _, spawns, _ = ce.summarize_log(_log(), "//test/")
        unreached = ce.not_reached(graph, spawns)
        self.assertEqual(
            unreached, ["not_reached Action k8-fastbuild:test/d/3_place.odb"]
        )
        counts2, _, spawns2, _ = ce.summarize_log(_log(), "//test/")
        lines = ce.summary_lines(counts2, spawns2, [])
        self.assertEqual(lines[-1], "every action is a remote cache hit")

    def test_evidence_carries_not_reached(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "e.txt")
            counts, tools, spawns, _ = ce.summarize_log(_log(miss=True), "//test/")
            ce.write_evidence(
                path,
                [],
                counts,
                tools,
                spawns,
                ["not_reached Action k8-fastbuild:test/d/3_place.odb"],
            )
            with open(path) as fh:
                text = fh.read()
            self.assertIn("spawns 3 hit 2 ran 0 miss 1 not_reached 1\n", text)
            self.assertTrue(
                text.endswith("not_reached Action k8-fastbuild:test/d/3_place.odb\n")
            )
            header, _, _ = ce._read(path)
            self.assertEqual(
                header["not_reached"], ["Action k8-fastbuild:test/d/3_place.odb"]
            )

    def test_sandboxed_pids(self):
        with tempfile.TemporaryDirectory() as d:
            ob = os.path.join(d, "ob")
            root = os.path.join(ob, "sandbox") + os.sep
            proc = os.path.join(d, "proc")
            os.makedirs(os.path.join(root, "processwrapper-sandbox", "7", "execroot"))
            os.makedirs(os.path.join(d, "elsewhere"))

            def fake(pid, cmdline, cwd):
                p = os.path.join(proc, str(pid))
                os.makedirs(p)
                with open(os.path.join(p, "cmdline"), "wb") as fh:
                    fh.write(cmdline.replace(" ", "\0").encode())
                os.symlink(cwd, os.path.join(p, "cwd"))

            # the action's process: cwd in the sandbox, relative command
            fake(
                11,
                "bazel-out/k8-opt-exec/bin/openroad -exit x.tcl",
                root + "processwrapper-sandbox/7/execroot",
            )
            # Bazel's wrapper: names the sandbox, cwd elsewhere
            fake(
                12,
                "process-wrapper --stats=" + root + "processwrapper-sandbox/7/stats",
                os.path.join(d, "elsewhere"),
            )
            # the server and an unrelated process
            fake(
                13,
                "bazel(x) -Dlog=" + ob + "/javalog.properties",
                os.path.join(d, "elsewhere"),
            )
            fake(14, "vim notes.txt", os.path.join(d, "elsewhere"))
            # a process whose cwd the sandbox cleanup already removed
            fake(15, "make", root + "processwrapper-sandbox/6/execroot (deleted)")
            os.makedirs(os.path.join(proc, "self"))
            self.assertEqual(
                sorted(ce.sandboxed_pids(root, proc, self_pid=0)), [11, 12, 15]
            )
            self.assertEqual(
                sorted(ce.sandboxed_pids(root, proc, self_pid=11)), [12, 15]
            )


if __name__ == "__main__":
    unittest.main()
