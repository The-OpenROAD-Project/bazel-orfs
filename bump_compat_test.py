"""Enforce the bumper's compatibility-cleanup policy.

``//:bump`` supports a rolling window of MODULE.bazel shapes (see
docs/openroad.md, "Supported window").  The window cuts both ways: a
compatibility branch kept for an old shape gets the same
``BUMP_SUPPORT_WINDOW_DAYS`` days, then it goes.

Every such branch is introduced with a marker naming the date the old
shape stopped being written::

    # COMPAT(2026-08-27): consumers bumped before this date pin openroad
    # via git_override; drop this branch once the window has passed.

Markers are measured against ``bump_reference_date.txt`` — the commit date
of the ORFS pin, written into the tree by //:bump — and never against the
clock.  A given tree therefore always produces the same verdict: re-running
an old build cannot turn it red, and a red build cannot be waited out.

This test fails once a marker is older than the window.  The fix is to
delete the code the marker guards — never to re-date the marker.
"""

import datetime
import os
import re
import tempfile
import unittest

import bump_impl

COMPAT_MARKER = re.compile(r"#\s*COMPAT\((\d{4}-\d{2}-\d{2})\)")

SCANNED_FILES = ["bump_impl.py"]

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def find_compat_markers(text):
    """Return ``(line number, date)`` for every COMPAT marker in ``text``."""
    markers = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = COMPAT_MARKER.search(line)
        if m:
            markers.append((lineno, datetime.date.fromisoformat(m.group(1))))
    return markers


def stale_markers(text, name, reference):
    """Return one message per COMPAT marker older than the window."""
    stale = []
    for lineno, marked in find_compat_markers(text):
        age = (reference - marked).days
        if age > bump_impl.BUMP_SUPPORT_WINDOW_DAYS:
            stale.append(f"{name}:{lineno} is {age} commit-days old ({marked})")
    return stale


class TestCompatMarkerScanner(unittest.TestCase):
    """The scanner itself, so this test means something with zero markers."""

    def test_finds_marker_with_line_number(self):
        text = "a = 1\n# COMPAT(2026-01-02): drop me\nb = 2\n"
        self.assertEqual(find_compat_markers(text), [(2, datetime.date(2026, 1, 2))])

    def test_finds_indented_and_trailing_markers(self):
        text = "    # COMPAT(2026-01-02): x\nz = 1  # COMPAT(2026-03-04): y\n"
        self.assertEqual(
            [d for _, d in find_compat_markers(text)],
            [datetime.date(2026, 1, 2), datetime.date(2026, 3, 4)],
        )

    def test_ignores_prose(self):
        self.assertEqual(find_compat_markers("# COMPAT: someday\n"), [])


class TestReferenceDate(unittest.TestCase):
    """The anchor is read from the tree, so no test here reads the clock."""

    def test_reads_date_past_comments(self):
        text = "# a comment\n# another\n2026-08-27\n"
        self.assertEqual(
            bump_impl.read_reference_date(text), datetime.date(2026, 8, 27)
        )

    def test_rejects_a_file_without_a_date(self):
        with self.assertRaises(ValueError):
            bump_impl.read_reference_date("# only comments\n")

    def test_round_trips_what_bump_writes(self):
        with tempfile.TemporaryDirectory() as workspace:
            moment = datetime.datetime(2026, 8, 27, 12, 0, tzinfo=datetime.timezone.utc)
            path = bump_impl.write_reference_date(workspace, moment)
            with open(path) as f:
                self.assertEqual(bump_impl.read_reference_date(f.read()), moment.date())


class TestStaleMarkerDetection(unittest.TestCase):
    """The rule itself, exercised against explicit dates."""

    REFERENCE = datetime.date(2026, 8, 27)

    def test_marker_at_the_window_edge_survives(self):
        edge = self.REFERENCE - datetime.timedelta(
            days=bump_impl.BUMP_SUPPORT_WINDOW_DAYS
        )
        self.assertEqual(
            stale_markers(f"# COMPAT({edge}): x\n", "f.py", self.REFERENCE), []
        )

    def test_marker_past_the_window_is_reported(self):
        past = self.REFERENCE - datetime.timedelta(
            days=bump_impl.BUMP_SUPPORT_WINDOW_DAYS + 1
        )
        self.assertEqual(
            len(stale_markers(f"# COMPAT({past}): x\n", "f.py", self.REFERENCE)), 1
        )

    def test_marker_ahead_of_the_reference_survives(self):
        ahead = self.REFERENCE + datetime.timedelta(days=1)
        self.assertEqual(
            stale_markers(f"# COMPAT({ahead}): x\n", "f.py", self.REFERENCE), []
        )


class TestCompatMarkersWithinWindow(unittest.TestCase):
    """No compatibility branch outlives the supported window."""

    def test_no_marker_older_than_the_window(self):
        with open(os.path.join(REPO_ROOT, bump_impl.BUMP_REFERENCE_DATE_FILE)) as f:
            reference = bump_impl.read_reference_date(f.read())

        stale = []
        for name in SCANNED_FILES:
            with open(os.path.join(REPO_ROOT, name)) as f:
                stale.extend(stale_markers(f.read(), name, reference))

        self.assertEqual(
            stale,
            [],
            "Compatibility code older than "
            f"{bump_impl.BUMP_SUPPORT_WINDOW_DAYS} days must be deleted, not "
            "maintained — see docs/openroad.md, 'Cleanup policy'. Stale "
            "markers: " + "; ".join(stale),
        )


if __name__ == "__main__":
    unittest.main()
