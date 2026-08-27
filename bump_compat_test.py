#!/usr/bin/env python3
"""Enforce the bumper's compatibility-cleanup policy.

``//:bump`` supports a rolling window of MODULE.bazel shapes (see
docs/openroad.md, "Supported window").  The window cuts both ways: a
compatibility branch kept for an old shape gets the same
``BUMP_SUPPORT_WINDOW_DAYS`` days, then it goes.

Every such branch is introduced with a marker naming the date the old
shape stopped being written::

    # COMPAT(2026-08-27): consumers bumped before this date pin openroad
    # via git_override; drop this branch once the window has passed.

This test fails once a marker is older than the window.  The fix is to
delete the code the marker guards — never to re-date the marker.
"""

import datetime
import os
import re
import unittest

import bump_impl

COMPAT_MARKER = re.compile(r"#\s*COMPAT\((\d{4}-\d{2}-\d{2})\)")

SCANNED_FILES = ["bump_impl.py"]


def find_compat_markers(text):
    """Return ``(line number, date)`` for every COMPAT marker in ``text``."""
    markers = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = COMPAT_MARKER.search(line)
        if m:
            markers.append((lineno, datetime.date.fromisoformat(m.group(1))))
    return markers


class TestCompatMarkerScanner(unittest.TestCase):
    """The scanner itself, so this test means something with zero markers."""

    def test_finds_marker_with_line_number(self):
        text = "a = 1\n# COMPAT(2026-01-02): drop me\nb = 2\n"
        self.assertEqual(
            find_compat_markers(text), [(2, datetime.date(2026, 1, 2))]
        )

    def test_finds_indented_and_trailing_markers(self):
        text = "    # COMPAT(2026-01-02): x\nz = 1  # COMPAT(2026-03-04): y\n"
        self.assertEqual(
            [d for _, d in find_compat_markers(text)],
            [datetime.date(2026, 1, 2), datetime.date(2026, 3, 4)],
        )

    def test_ignores_prose(self):
        self.assertEqual(find_compat_markers("# COMPAT: someday\n"), [])


class TestCompatMarkersWithinWindow(unittest.TestCase):
    """No compatibility branch outlives the supported window."""

    def test_no_marker_older_than_the_window(self):
        today = datetime.date.today()
        stale = []
        for name in SCANNED_FILES:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            with open(path) as f:
                for lineno, marked in find_compat_markers(f.read()):
                    age = (today - marked).days
                    if age > bump_impl.BUMP_SUPPORT_WINDOW_DAYS:
                        stale.append(f"{name}:{lineno} is {age} days old ({marked})")
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
