"""What the harvester must not get wrong.

The fixtures are excerpts of a real 3_3_place_gp.log, stamped the way
`--//:log_timestamps` stamps it, because every trap here is a formatting
one: a prefix in front of the line, a gpl row whose trailing columns are
blank, a run that printed a plausible last overflow and still failed.
"""

import unittest

import harvest

CONVERGED = """
[     0.00] [INFO ORD-0030] Using 16 thread(s).
[     1.20] ESTDENSITY_JSON {"kind": "context", "design": "gcd", \
"uniform_density": 0.2109, "pad": 0, "place_density": "", \
"place_density_lb_addon": "0.25", "command_available": 1}
[     1.90] ESTDENSITY_JSON {"kind": "estimate", "overflow": 0.05, \
"estimated_density": 0.7421, "uniform_density": 0.2109, "elapsed_s": 0.41}
[     2.30] ESTDENSITY_JSON {"kind": "estimate", "overflow": 0.1, \
"estimated_density": 0.6640, "uniform_density": 0.2109, "elapsed_s": 0.39}
[     2.70] ESTDENSITY_JSON {"kind": "estimate", "overflow": 0.2, \
"estimated_density": 0.5468, "uniform_density": 0.2109, "elapsed_s": 0.38}
[     3.10] Placement density is 0.4131, computed from PLACE_DENSITY_LB_ADDON \
      0.25 and lower bound 0.2109
[     4.00]         0 |   0.9832 |  1.234560e+04 |          |           |
[     5.00]        10 |   0.4211 |  1.100000e+04 |          |           |
[     6.00]        20 |   0.0921 |  1.050000e+04 |          |           |
[     7.00] [INFO GPL-1014] Final placement area: 100.00 (+0.00%)
"""

MISSED = """
[     0.00] [INFO ORD-0030] Using 16 thread(s).
[     3.10] Placement density is 0.2209, computed from PLACE_DENSITY_LB_ADDON \
      0.0 and lower bound 0.2109
[     4.00]         0 |   0.9832 |  1.234560e+04 |          |           |
[     5.00]      2000 |   0.1042 |  1.050000e+04 |          |           |
[     6.00] [WARNING GPL-1010] GPL reached the maximum number of iterations \
for nesterov 2000. Placement may have failed to converge.
"""

# gpl's own binary search giving up, exactly as it appears: the warning
# is printed by the call that is about to print the probe's line.
SEARCH_GAVE_UP = """
[     1.29] [INFO GPL-0088] Initialize gpl and estimate target density.
[     1.29] ESTDENSITY_JSON {"kind": "estimate", "overflow": 0.05, \
"estimated_density": 0.8760, "uniform_density": 0.78, "elapsed_s": 0.002}
[     1.29] [INFO GPL-0088] Initialize gpl and estimate target density.
[     1.29] [WARNING GPL-0186] Binary search didn't converge after 20 iterations. \
The best density found was 0.78, with an overflow of 0.55210.
[     1.29] ESTDENSITY_JSON {"kind": "estimate", "overflow": 0.1, \
"estimated_density": 0.7800002, "uniform_density": 0.78, "elapsed_s": 0.001}
"""

BUFFERED = """
[     1.29] [INFO RSZ-0026] Removed 43 buffers.
[     1.29] Perform port buffering...
[     1.30] [INFO RSZ-0027] Inserted 35 BUFx2_ASAP7_75t_R input buffers.
[     1.30] [INFO RSZ-0028] Inserted 18 BUFx2_ASAP7_75t_R output buffers.
"""

NO_COMMAND = """
[     1.20] ESTDENSITY_JSON {"kind": "context", "design": "gcd", \
"uniform_density": 0.2109, "pad": 0, "place_density": "0.60", \
"place_density_lb_addon": "", "command_available": 0}
[     1.21] ESTDENSITY_JSON {"kind": "skipped", \
"reason": "estimate_target_density not in this binary"}
"""


class HarvestTest(unittest.TestCase):
    def test_estimates_are_keyed_by_overflow(self):
        estimates = harvest.estimates(CONVERGED)
        self.assertEqual(sorted(estimates), [0.05, 0.1, 0.2])
        self.assertAlmostEqual(estimates[0.1]["estimated_density"], 0.6640)

    def test_context_carries_what_the_design_ships(self):
        context = harvest.context(CONVERGED)
        self.assertEqual(context["design"], "gcd")
        self.assertEqual(context["place_density_lb_addon"], "0.25")

    def test_orfs_density_survives_the_tcl_line_continuation(self):
        density = harvest.orfs_density(CONVERGED)
        self.assertAlmostEqual(density["density"], 0.4131)
        self.assertAlmostEqual(density["addon"], 0.25)
        self.assertAlmostEqual(density["uniform_density"], 0.2109)

    def test_converged_run(self):
        gp = harvest.gp_result(CONVERGED)
        self.assertTrue(gp["converged"])
        self.assertEqual(gp["final_iter"], 20)
        self.assertAlmostEqual(gp["final_overflow"], 0.0921)
        self.assertEqual(gp["iterations"], 3)

    def test_max_iterations_is_not_convergence(self):
        # The last row reads 0.1042, close enough to look fine; gpl said
        # it ran out of iterations, and that is what decides.
        gp = harvest.gp_result(MISSED)
        self.assertFalse(gp["converged"])
        self.assertTrue(gp["hit_max_iter"])

    def test_overflow_just_above_target_is_a_miss(self):
        gp = harvest.gp_result(MISSED, overflow=0.2)
        self.assertFalse(gp["converged"], "the max-iter warning still decides")

    def test_unpatched_binary_reports_rather_than_raises(self):
        context = harvest.context(NO_COMMAND)
        self.assertEqual(context["command_available"], 0)
        self.assertEqual(harvest.estimates(NO_COMMAND), {})

    def test_an_answer_gpl_disowned_is_marked(self):
        estimates = harvest.estimates(SEARCH_GAVE_UP)
        self.assertTrue(estimates[0.05]["search_converged"])
        self.assertFalse(
            estimates[0.1]["search_converged"],
            "GPL-0186 belongs to the estimate printed after it",
        )

    def test_a_clean_search_is_not_marked_as_failed(self):
        for record in harvest.estimates(CONVERGED).values():
            self.assertTrue(record["search_converged"])

    def test_buffer_churn_between_the_probe_and_the_placer(self):
        # The gap the probe cannot avoid: ORFS runs the hook before
        # remove_buffers and buffer_ports, so this is how much the design
        # changed after the estimate was taken.
        churn = harvest.buffer_churn(BUFFERED)
        self.assertEqual(churn["removed"], 43)
        self.assertEqual(churn["inserted_input"], 35)
        self.assertEqual(churn["inserted_output"], 18)

    def test_no_buffering_reads_as_zero_not_as_missing(self):
        self.assertEqual(
            harvest.buffer_churn(CONVERGED),
            {"removed": 0, "inserted_input": 0, "inserted_output": 0},
        )

    def test_thread_witness(self):
        self.assertEqual(harvest.threads(CONVERGED), 16)
        self.assertIsNone(harvest.threads(NO_COMMAND))

    def test_a_truncated_probe_line_is_an_error_not_a_zero(self):
        with self.assertRaises(ValueError):
            harvest.estimates('ESTDENSITY_JSON {"kind": "estim')


if __name__ == "__main__":
    unittest.main()
