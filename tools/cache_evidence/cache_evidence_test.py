"""cache_evidence on hand-encoded execution logs and aquery graphs."""

import json
import os
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
    def test_scope(self):
        counts, spawns = ce.summarize_log(_log(), "//test/")
        self.assertEqual(
            counts, {"spawns": 3, "hit": 3, "ran": 0, "miss": 0, "outside": []}
        )
        # The out-of-scope tool build is counted, not itemized.
        self.assertEqual(
            spawns,
            [
                ("hit", "Action", "k8-fastbuild:test/d/1_synth.v"),
                ("hit", "Action", "k8-fastbuild:test/d/2_floorplan.odb"),
            ],
        )

    def test_miss(self):
        counts, spawns = ce.summarize_log(_log(miss=True), "//test/")
        self.assertEqual(counts["miss"], 1)
        self.assertEqual(
            spawns[1], ("miss", "Action", "k8-fastbuild:test/d/2_floorplan.odb")
        )

    def test_truncated_log(self):
        counts, _ = ce.summarize_log(_log()[:-5], "//test/")
        self.assertEqual(counts["spawns"], 2)

    def test_zstd_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.zst")
            with open(path, "wb") as fh:
                fh.write(zstandard.ZstdCompressor().compress(_log()))
            self.assertEqual(ce._decompress(path), _log())

    def test_capture_refuses_a_build_with_no_actions(self):
        none = {"spawns": 0, "hit": 0, "ran": 0, "miss": 0}
        why = ce.capture_refusal(none, "INFO: x\nERROR: no such package 'y'\n")
        self.assertEqual(why, "ERROR: no such package 'y'")
        self.assertEqual(ce.capture_refusal(none, ""), "the build logged no actions")
        self.assertIsNone(ce.capture_refusal(dict(none, spawns=3, hit=3), "ERROR: x"))


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
        counts, spawns = ce.summarize_log(_log(miss=True), "//test/")
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
        counts, spawns = ce.summarize_log(_log(miss=True), "//test/d:s")
        self.assertEqual(
            counts["outside"],
            ["miss Action k8-fastbuild:test/d/2_floorplan.odb (outside --scope)"],
        )
        self.assertIn(counts["outside"][0], ce.summary_lines(counts, spawns, []))

    def test_all_hits_say_so(self):
        graph = ce.graph_actions(self.GRAPH, "//test/", "//test/d:place")
        counts, spawns = ce.summarize_log(_log(), "//test/")
        unreached = ce.not_reached(graph, spawns)
        self.assertEqual(
            unreached, ["not_reached Action k8-fastbuild:test/d/3_place.odb"]
        )
        counts2, spawns2 = ce.summarize_log(_log(), "//test/")
        lines = ce.summary_lines(counts2, spawns2, [])
        self.assertEqual(lines[-1], "every action is a remote cache hit")

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
