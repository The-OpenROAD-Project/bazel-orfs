"""webclient against a fake web viewer, and the pin-access log parser."""

import socket
import unittest

import fake_viewer
import odbdebug
import webclient


def handler(cmd):
    """expr -> EXPR; long -> 70000 characters; boom -> an error frame;
    pause N -> N logged debug pauses."""
    if cmd == "boom":
        return {"error": "no such request"}
    if cmd == "long":
        return {"result": "x" * 70000}
    if cmd.startswith("pause "):
        n = int(cmd.split()[1])
        return {
            "result": "done",
            "log": ["step %d" % k for k in range(n)],
            "pauses": n,
        }
    return {"result": cmd.upper()}


class WebClientTest(unittest.TestCase):
    def test_tcl_round_trip(self):
        fake = fake_viewer.FakeViewer(handler)
        v = webclient.Viewer(fake.port, timeout=10)
        try:
            out = v.tcl("expr")
            self.assertEqual(out["result"], "EXPR")
            self.assertFalse(out["is_error"])
            self.assertEqual(out["pauses"], 0)
            self.assertEqual(len(v.tcl("long")["result"]), 70000)
        finally:
            v.close()

    def test_every_pause_is_continued_and_logged(self):
        fake = fake_viewer.FakeViewer(handler)
        v = webclient.Viewer(fake.port, timeout=10)
        try:
            out = v.tcl("pause 3")
        finally:
            v.close()
        self.assertEqual(out["result"], "done")
        self.assertEqual(out["pauses"], 3)
        self.assertEqual(out["log"], "step 0\nstep 1\nstep 2")
        kinds = [m["type"] for m in fake.received]
        self.assertEqual(kinds.count("debug_continue"), 3)

    def test_error_reply_raises(self):
        fake = fake_viewer.FakeViewer(handler)
        v = webclient.Viewer(fake.port, timeout=10)
        try:
            with self.assertRaises(webclient.WebError):
                v.tcl("boom")
        finally:
            v.close()

    def test_unreachable(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with self.assertRaises(webclient.WebError):
            webclient.Viewer(port)


# What detailed_route_debug -pa -pa_markers logs, cut down from a real run
# on an asap7 block pin two wire widths wide.
PA_LOG = """[INFO DRT-4000] DEBUGGING inst u_blk term p36
[INFO DRT-0165] Start pin access.
[INFO DRT-0292] Marker frcLef58RectOnlyConstraint at (6480, 12502) (6498, 12538).
[INFO DRT-0292] Marker frcLef58RectOnlyConstraint at (6480, 12502) (6498, 12538).
[INFO DRT-0292] Marker frcLef58EolKeepOutConstraint at (6498, 12880) (6507, 12900).
Via VIA34 markers 2
[INFO DRT-0119] Marker (6411, 12528) (6509, 12552) on M4:
Short
[INFO DRT-0119] Marker (6471, 12520) (6489, 12541) on M3:
RECTONLY exceptNonCorePins false
Via VIA34 markers 0
Via VIA34 markers 1
[INFO DRT-0119] Marker (6480, 12880) (6498, 12884) on M3:
EOLKEEPOUT backwardExt 0 sideExt 13 forwardExt 31 eolWidth 25 cornerOnly true exceptWithin false withinLow 0 withinHigh 0
[ERROR DRT-0073] No access point for u_blk/p36 (BLK)."""


class ParsePaLogTest(unittest.TestCase):
    def test_groups_markers_by_constraint(self):
        s = odbdebug.parse_pa_log(PA_LOG)
        self.assertEqual(
            s["planar_markers"]["frcLef58RectOnlyConstraint"],
            {"count": 1, "boxes": [[6480, 12502, 6498, 12538]]},
        )
        self.assertEqual(
            s["planar_markers"]["frcLef58EolKeepOutConstraint"]["count"], 1
        )
        # The candidate with no markers was accepted, not rejected.
        self.assertEqual(s["via_candidates_rejected"], 2)
        self.assertEqual(
            sorted(s["via_markers"]),
            [
                "EOLKEEPOUT on M3",
                "RECTONLY exceptNonCorePins false on M3",
                "Short on M4",
            ],
        )
        self.assertTrue(s["no_access_point"])
        self.assertEqual(s["message_limit_hit"], [])

    def test_reports_the_logger_limit(self):
        crossing = PA_LOG + "\n[WARNING DRT-0119] message limit (1000) reached."
        self.assertEqual(
            odbdebug.parse_pa_log(crossing)["message_limit_hit"], ["DRT-0119"]
        )
        # After the limit: via candidates rejected with none of their markers.
        later = "Via VIA34 markers 3\nVia VIA34 markers 1"
        s = odbdebug.parse_pa_log(later)
        self.assertEqual(s["via_markers"], {})
        self.assertEqual(s["message_limit_hit"], ["DRT-0119"])


if __name__ == "__main__":
    unittest.main()
