"""cache_evidence on hand-encoded execution logs."""

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


def _log(tool_digest="aa", miss=False):
    """A tool, a flow script, a design input; two actions, one downstream."""
    entries = [
        _entry(
            1,
            ce._FILE,
            _file("bazel-out/k8-opt-exec/bin/external/yosys+/yosys", tool_digest),
        ),
        _entry(2, ce._FILE, _file("external/orfs/flow/scripts/synth.tcl", "bb")),
        _entry(3, ce._FILE, _file("test/d/constraints.sdc", "cc")),
        _entry(4, ce._INPUT_SET, _len(5, _varint(1) + _varint(2))),
        _entry(5, ce._INPUT_SET, _len(5, _varint(3)) + _len(4, _varint(4))),
        _entry(6, ce._FILE, _file("bazel-out/k8-fastbuild/bin/test/d/1_synth.v", "dd")),
        _entry(7, ce._SPAWN, _spawn("//test/d:synth", 6, 5, "key1" + tool_digest)),
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
        counts, tools, spawns = ce.summarize_log(_log(), "//test/")
        self.assertEqual(counts, {"spawns": 3, "hit": 3, "ran": 0, "miss": 0})
        # The out-of-scope tool build is counted, not itemized.
        self.assertEqual(len(spawns), 2)
        self.assertIn("hit Action k8-fastbuild:test/d/1_synth.v", spawns[0])
        self.assertEqual(len(tools), 1)
        self.assertIn("k8-opt-exec:external/yosys+", tools[0])
        # No action here has an environment; the empty hash is stable.
        self.assertIn("env=" + ce._h([]), spawns[0])

    def test_miss(self):
        counts, _, spawns = ce.summarize_log(_log(miss=True), "//test/")
        self.assertEqual(counts["miss"], 1)
        self.assertIn(" miss Action k8-fastbuild:test/d/2_floorplan.odb", spawns[1])

    def test_truncated_log(self):
        data = _log()
        counts, _, spawns = ce.summarize_log(data[:-5], "//test/")
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
        counts, tools, spawns = ce.summarize_log(log, "//test/")
        ce.write_evidence(path, header, counts, tools, spawns)
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


class RedactTest(unittest.TestCase):
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
            ce.redact_option("--action_env=PATH=/usr/bin"), "--action_env=PATH=<redacted>"
        )
        # any other value that names an address is dropped whole
        self.assertEqual(
            ce.redact_option("--some_flag=user@corp.example.com"), "--some_flag=<redacted>"
        )
        ce.check_public([ce.redact_option("--repo_env=A=b@corp.example.com")])

    def test_capture_refuses_a_build_with_no_actions(self):
        none = {"spawns": 0, "hit": 0, "ran": 0, "miss": 0}
        why = ce.capture_refusal(
            none,
            "INFO: x\nERROR: 'linux-sandbox' was requested for explicit default"
            " strategies but no strategy with that identifier was registered.\n",
        )
        self.assertIn("linux-sandbox", why)
        self.assertIn("apparmor_restrict_unprivileged_userns", why)
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


if __name__ == "__main__":
    unittest.main()
