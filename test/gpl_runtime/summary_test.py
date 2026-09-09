"""The two reducers against the perf script formats they parse."""

import io
import unittest

import callgraph_summary
import perf_summary

FLAT = (
    "        openroad  79765 28484.329895:   21216994 cpu/cycles/P:"
    "            5a5638 gpl::GNet::updateBox()+0x1a (/x/openroad)\n"
)
SPIN = (
    "        openroad  79766 28484.329900:   21216994 cpu/cycles/P:"
    "            5125f32 kmp_flag_64<false, true>::wait(kmp_info*, int)+0x5e2 (/x/openroad)\n"
)
ELAPSED = (
    "Elapsed time: 0:39.42[h:]min:sec. CPU time: user 1360.07 sys 96.24 (3694%). "
    "Peak memory: 898540KB."
)


class PerfSummaryTest(unittest.TestCase):
    def test_sample_line(self):
        m = perf_summary.SAMPLE.match(FLAT)
        self.assertEqual(m.group("comm"), "openroad")
        self.assertEqual(m.group("tid"), "79765")
        self.assertEqual(m.group("sym"), "gpl::GNet::updateBox()+0x1a")
        self.assertTrue(
            perf_summary.SPIN.match(perf_summary.SAMPLE.match(SPIN).group("sym"))
        )

    def test_elapsed(self):
        e = perf_summary.parse_elapsed(ELAPSED)
        self.assertAlmostEqual(e["wall_s"], 39.42)
        self.assertEqual(e["cpu_pct"], 3694)
        self.assertAlmostEqual(e["peak_mb"], 898540 / 1024)

    def test_category(self):
        self.assertEqual(
            perf_summary.category("kmp_flag_64<false, true>::wait"), "OpenMP wait"
        )
        self.assertEqual(
            perf_summary.category("gpl::GNet::updateBox"), "wirelength gradient"
        )
        self.assertEqual(
            perf_summary.category("Eigen::internal::sparse_time_dense_product_impl"),
            "initial place (Eigen)",
        )


class CallGraphFormatTest(unittest.TestCase):
    def test_iter_samples_reads_both_formats(self):
        text = (
            FLAT
            + "openroad  557968 30196.682988:   20437256 cpu/cycles/P: \n"
            + "\t         5125f32 kmp_flag_64<false, true>::wait(kmp_info*, int)+0x5e2 (/x/openroad)\n"
            + "\t         5120537 __kmp_hyper_barrier_release(barrier_type, kmp_info*, int, int, int)+0x107 (/x/openroad)\n"
            + "\n"
        )
        got = list(perf_summary.iter_samples(io.StringIO(text)))
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0][3], "gpl::GNet::updateBox()+0x1a")
        self.assertEqual(got[1][1], "557968")
        self.assertEqual(got[1][3], "kmp_flag_64<false, true>::wait(kmp_info*, int)")


class CallgraphSummaryTest(unittest.TestCase):
    def test_header_and_frame(self):
        self.assertIsNotNone(
            callgraph_summary.HEADER.match(
                "openroad  557968 30196.682988:   20437256 cpu/cycles/P: "
            )
        )
        m = callgraph_summary.FRAME.match(
            "\t         5125f32 kmp_flag_64<false, true>::wait(kmp_info*, int)+0x5e2 (/x/openroad)"
        )
        self.assertEqual(
            m.group("sym"), "kmp_flag_64<false, true>::wait(kmp_info*, int)"
        )

    def test_attribute_skips_wrappers_and_outlined_bodies(self):
        # Leaf first, as perf script prints them.
        frames = [
            "gpl::NesterovBaseCommon::getWireLengthGradientPinWA(gpl::GPin const*, float, float) const",
            "gpl::NesterovBaseCommon::updateWireLengthForceWA_native(float, float) [clone .omp_outlined]",
            "__kmp_invoke_microtask",
            "__kmpc_fork_call",
            "gpl::NesterovBaseCommon::updateWireLengthForceWA_native(float, float)",
            "gpl::NesterovPlace::doBackTracking()",
            "gpl::NesterovPlace::doNesterovPlace(int)",
            "gpl::Replace::doNesterovPlace(int, gpl::PlaceOptions const&, int)",
            "main",
        ]
        phase, target = callgraph_summary.attribute(frames)
        self.assertEqual(phase, "Nesterov")
        self.assertEqual(target, "gpl::NesterovPlace::doBackTracking()")


if __name__ == "__main__":
    unittest.main()
