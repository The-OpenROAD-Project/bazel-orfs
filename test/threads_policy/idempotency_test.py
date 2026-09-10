#!/usr/bin/env python3
"""The whole point of this module is telling two findings apart.

So most of these tests are pairs: the same shape of disagreement,
arranged once as nondeterminism and once as thread-dependence, asserted
to come out as different verdicts. #968's check pooled both into "more
than one hash" and would pass every test here with one answer.
"""

import unittest

import idempotency


def arms(**kwargs):
    """arms(t1=("a", "a"), t16=("b", "b")) -> {1: {1: "a", 2: "a"}, ...}"""
    out = {}
    for name, values in kwargs.items():
        threads = int(name[1:])
        out[threads] = {i + 1: v for i, v in enumerate(values)}
    return out


def record(design="asap7_gcd", stage="cts", threads=1, repeat=1, step="4_1_cts", **kw):
    sample = {"ran": True}
    sample.update(kw)
    return {
        "design": design,
        "stage": stage,
        "threads": threads,
        "repeat": repeat,
        "substeps": {step: sample},
    }


class TheDistinction(unittest.TestCase):
    def test_every_arm_agreeing_is_stable(self):
        got = idempotency.classify(arms(t1=("a", "a"), t8=("a", "a"), t16=("a", "a")))
        self.assertEqual(got.verdict, idempotency.STABLE)
        self.assertIsNone(got.first_divergent_arm)

    def test_an_arm_disagreeing_with_itself_is_run_to_run(self):
        # Not a thread finding at all: it would show up at one thread.
        got = idempotency.classify(arms(t1=("a", "a"), t16=("b", "c")))
        self.assertEqual(got.verdict, idempotency.RUN_TO_RUN)
        self.assertEqual(got.unstable_arms, [16])

    def test_arms_agreeing_with_themselves_but_not_each_other_is_thread_dependent(self):
        got = idempotency.classify(arms(t1=("a", "a"), t8=("a", "a"), t16=("b", "b")))
        self.assertEqual(got.verdict, idempotency.THREAD_DEPENDENT)
        self.assertEqual(got.first_divergent_arm, 16)

    def test_the_reference_itself_being_unstable_is_run_to_run(self):
        # And specifically not thread-dependent: a base that disagrees
        # with itself cannot establish that another arm disagrees.
        got = idempotency.classify(arms(t1=("a", "b"), t16=("c", "c")))
        self.assertEqual(got.verdict, idempotency.RUN_TO_RUN)

    def test_both_at_once_is_confounded_and_does_not_claim_a_thread_bug(self):
        got = idempotency.classify(arms(t1=("a", "a"), t8=("b", "b"), t16=("c", "d")))
        self.assertEqual(got.verdict, idempotency.CONFOUNDED)

    def test_confounded_is_read_before_thread_dependent(self):
        self.assertLess(
            idempotency.SEVERITY.index(idempotency.CONFOUNDED),
            idempotency.SEVERITY.index(idempotency.THREAD_DEPENDENT),
        )


class FirstDivergence(unittest.TestCase):
    def test_the_lowest_diverging_arm_is_reported_not_the_last(self):
        # The ceiling is set by where it first breaks.
        got = idempotency.classify(
            arms(t1=("a", "a"), t4=("b", "b"), t8=("b", "b"), t16=("c", "c"))
        )
        self.assertEqual(got.first_divergent_arm, 4)

    def test_the_safe_ceiling_is_the_arm_below_the_first_divergence(self):
        records = [
            record(threads=t, repeat=r, odb_sha1=("a" if t < 8 else "b"))
            for t in (1, 2, 4, 8, 16)
            for r in (1, 2)
        ]
        ceiling = idempotency.safe_ceiling(idempotency.verdicts(records))
        self.assertEqual(ceiling[("asap7_gcd", "cts")], 4)

    def test_run_to_run_sets_no_ceiling_because_no_count_is_safe(self):
        records = [
            record(threads=t, repeat=r, odb_sha1=("a" if r == 1 else "b"))
            for t in (1, 16)
            for r in (1, 2)
        ]
        self.assertEqual(idempotency.safe_ceiling(idempotency.verdicts(records)), {})


class Unproven(unittest.TestCase):
    def test_a_missing_witness_is_unproven_not_stable(self):
        # Silence is not agreement. #968's own bug was in this shape:
        # a witness that silently became None read as identical.
        got = idempotency.classify(arms(t1=(None, None), t16=(None, None)))
        self.assertEqual(got.verdict, idempotency.UNPROVEN)
        self.assertIn("witness missing", got.detail)

    def test_a_ladder_with_no_reference_arm_is_unproven(self):
        got = idempotency.classify(arms(t8=("a", "a"), t16=("a", "a")))
        self.assertEqual(got.verdict, idempotency.UNPROVEN)
        self.assertIn("no t=1 arm", got.detail)

    def test_the_reference_alone_is_unproven_however_stable_it_is(self):
        # A ladder of one arm establishes nothing about invariance. An
        # earlier version called this `stable`, which is exactly the
        # over-claim this module exists to avoid.
        got = idempotency.classify(arms(t1=("a", "a")))
        self.assertEqual(got.verdict, idempotency.UNPROVEN)
        self.assertIn("only the t=1 reference", got.detail)

    def test_a_real_divergence_outranks_a_missing_witness(self):
        got = idempotency.classify(arms(t1=("a", "a"), t8=(None, None), t16=("b", "b")))
        self.assertEqual(got.verdict, idempotency.THREAD_DEPENDENT)


class Witnesses(unittest.TestCase):
    def test_each_witness_gets_its_own_verdict(self):
        # A QoR divergence with an identical ODB is a divergence that
        # was repaired away -- the OpenROAD#9781 shape -- so collapsing
        # the witnesses into one answer would hide it.
        records = []
        for threads in (1, 16):
            for repeat in (1, 2):
                records.append(
                    record(
                        threads=threads,
                        repeat=repeat,
                        odb_sha1="same",
                        sdc_sha1="same",
                        qor={"design__instance__count__setup_buffer": threads},
                    )
                )
        got = {v.key.kind: v.verdict for v in idempotency.verdicts(records)}
        self.assertEqual(got["odb"], idempotency.STABLE)
        self.assertEqual(got["sdc"], idempotency.STABLE)
        self.assertEqual(got["qor"], idempotency.THREAD_DEPENDENT)

    def test_the_qor_dict_is_compared_by_value_not_identity(self):
        got = idempotency.classify(
            {
                1: {1: {"a": 1, "b": 2}, 2: {"b": 2, "a": 1}},
                16: {1: {"a": 1, "b": 2}, 2: {"a": 1, "b": 2}},
            }
        )
        self.assertEqual(got.verdict, idempotency.STABLE)


class Pinning(unittest.TestCase):
    def test_pinned_arms_are_excluded(self):
        # --pin changes the affinity mask as well as the thread count,
        # so a pinned arm differs from an unpinned one in two things
        # and cannot be its reference.
        records = [
            record(threads=1, repeat=1, odb_sha1="a"),
            record(threads=1, repeat=2, odb_sha1="a"),
            dict(record(threads=16, repeat=1, odb_sha1="b"), pinned=True),
        ]
        got = idempotency.verdicts(records)
        odb = [v for v in got if v.key.kind == "odb"][0]
        self.assertEqual(odb.verdict, idempotency.UNPROVEN)
        self.assertEqual(sorted(odb.arms), [1])


class AbsentWitness(unittest.TestCase):
    """A witness a stage cannot have is not a witness that went missing."""

    def test_a_field_the_sample_does_not_carry_gets_no_verdict(self):
        # `route` writes no .sdc from the substeps an arm runs, so an
        # sdc verdict for route would be a permanent `unproven` row
        # that reads as a defect in the harness.
        records = [
            {
                "design": "nangate45_gcd",
                "stage": "route",
                "threads": t,
                "repeat": r,
                "substeps": {"5_2_route": {"ran": True, "odb_sha1": "a", "qor": {}}},
            }
            for t in (1, 16)
            for r in (1, 2)
        ]
        kinds = {v.key.kind for v in idempotency.verdicts(records)}
        self.assertEqual(kinds, {"odb", "qor"})

    def test_a_field_present_but_empty_is_still_unproven(self):
        records = [
            record(threads=t, repeat=r, odb_sha1=None) for t in (1, 16) for r in (1, 2)
        ]
        odb = [v for v in idempotency.verdicts(records) if v.key.kind == "odb"][0]
        self.assertEqual(odb.verdict, idempotency.UNPROVEN)


class ThreadBlind(unittest.TestCase):
    def test_a_substep_that_never_went_parallel_is_flagged(self):
        # It measures nothing about thread policy, so a divergence
        # there is a nondeterminism finding in a thread study's
        # clothes.
        records = [
            record(threads=1, repeat=1, cpu_pct=99),
            record(threads=16, repeat=1, cpu_pct=104),
        ]
        self.assertEqual(
            idempotency.thread_blind(records), {("asap7_gcd", "cts", "4_1_cts")}
        )

    def test_a_substep_that_used_more_than_one_core_is_not(self):
        records = [record(threads=16, repeat=1, cpu_pct=1328)]
        self.assertEqual(idempotency.thread_blind(records), set())

    def test_the_peak_over_arms_decides_not_the_single_threaded_arm(self):
        # At t=1 every substep looks thread-blind.
        records = [
            record(threads=1, repeat=1, cpu_pct=99),
            record(threads=16, repeat=1, cpu_pct=900),
        ]
        self.assertEqual(idempotency.thread_blind(records), set())


class Indexing(unittest.TestCase):
    def test_a_substep_that_did_not_run_contributes_nothing(self):
        records = [
            record(threads=1, repeat=1, odb_sha1="a"),
            {
                "design": "asap7_gcd",
                "stage": "cts",
                "threads": 16,
                "repeat": 1,
                "substeps": {"4_1_cts": {"ran": False}},
            },
        ]
        arms_seen = idempotency.index(records)[
            idempotency.Key("asap7_gcd", "cts", "4_1_cts", "odb")
        ]
        self.assertEqual(sorted(arms_seen), [1])

    def test_designs_and_stages_do_not_pool(self):
        records = [
            record(design="asap7_gcd", threads=1, repeat=1, odb_sha1="a"),
            record(design="sky130hd_gcd", threads=1, repeat=1, odb_sha1="b"),
        ]
        designs = {v.key.design for v in idempotency.verdicts(records)}
        self.assertEqual(designs, {"asap7_gcd", "sky130hd_gcd"})


if __name__ == "__main__":
    unittest.main()
