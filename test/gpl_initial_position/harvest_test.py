"""Unit tests for the sample harvester's log parsing."""

import unittest

import harvest


class ElapsedTest(unittest.TestCase):
    def test_minutes_and_seconds(self):
        # ORFS annotates the format as [h:]min:sec, so two fields are
        # min:sec. Reading the first as hours inflates this 60-fold --
        # the bug this test exists to prevent coming back.
        self.assertAlmostEqual(
            harvest.elapsed_seconds("Elapsed time: 2:07.21[h:]min:sec"), 127.21
        )

    def test_sub_minute(self):
        self.assertAlmostEqual(
            harvest.elapsed_seconds("Elapsed time: 0:00.85[h:]min:sec"), 0.85
        )

    def test_just_under_an_hour(self):
        self.assertAlmostEqual(
            harvest.elapsed_seconds("Elapsed time: 59:59.99[h:]min:sec"), 3599.99
        )

    def test_three_field_form_with_hours(self):
        # The previous regex could not match this at all, so a step that
        # ran over an hour recorded no runtime rather than a wrong one.
        self.assertAlmostEqual(
            harvest.elapsed_seconds("Elapsed time: 1:02:03.50[h:]min:sec"), 3723.50
        )

    def test_absent_line_is_none(self):
        self.assertIsNone(harvest.elapsed_seconds("the step died first"))

    def test_a_long_step_is_not_confused_with_a_short_one(self):
        short = harvest.elapsed_seconds("Elapsed time: 0:07.00[h:]min:sec")
        long_ = harvest.elapsed_seconds("Elapsed time: 7:00.00[h:]min:sec")
        self.assertAlmostEqual(short, 7.0)
        self.assertAlmostEqual(long_, 420.0)
        self.assertGreater(long_, short)


if __name__ == "__main__":
    unittest.main()
