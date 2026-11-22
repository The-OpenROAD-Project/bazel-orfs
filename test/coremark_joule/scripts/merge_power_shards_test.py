#!/usr/bin/env python3
"""Unit tests for summing power shards.

What the sum must do: count every unit once, take a child's abstract
out of its parent's shard except for the nets it drives there, leave a
macro that is not a shard counted, and refuse a shard whose SAIF did
not bind rather than sum a default activity into a measurement.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from merge_power_shards import GROUPS, main, merge, unit_rows  # noqa: E402


def row(internal=0.0, switching=0.0, leakage=0.0):
    return {
        "internal": internal,
        "switching": switching,
        "leakage": leakage,
        "total": internal + switching + leakage,
    }


def design(**groups):
    d = {g: row() for g in GROUPS}
    d.update(groups)
    total = row()
    for g in GROUPS[:-1]:
        for k in ("internal", "switching", "leakage", "total"):
            total[k] += d[g][k]
    d["Total"] = total
    return d


def shard(unit, driven, less=None, children=(), kids=(), saif_pins=19):
    """kids: [(name, internal, switching, leakage)], both arms alike."""
    kid_rows = [dict(row(i, s, l), name=n) for n, i, s, l in kids]
    return {
        "unit": unit,
        "scope": "TOP/dut" + ("/" + unit if unit else ""),
        "children": list(children),
        "annotation": {"saif_pins": saif_pins, "pins": 20},
        "vectorless": {"design": less or driven, "children": kid_rows},
        "vector_driven": {"design": driven, "children": kid_rows},
    }


def parent(children=("u_a",), macro=row(1.0, 4.0, 2.0), extra_macro=row()):
    m = {k: macro[k] + extra_macro[k] for k in macro}
    return shard(
        "",
        design(Sequential=row(10.0, 1.0, 1.0), Macro=m),
        less=design(Sequential=row(20.0, 2.0, 1.0), Macro=m),
        children=children,
        kids=[
            (c, macro["internal"], macro["switching"], macro["leakage"])
            for c in children
        ],
    )


def block(unit="u_a"):
    return shard(
        unit,
        design(Sequential=row(5.0, 0.5, 3.0)),
        less=design(Sequential=row(6.0, 0.5, 3.0)),
    )


class MergeTest(unittest.TestCase):
    def test_child_keeps_its_switching(self):
        _, driven, _ = merge([parent(), block()])
        total = driven["Total"]
        # parent 10 + block 5; the abstract's internal 1 out
        self.assertAlmostEqual(total["internal"], 15.0)
        # parent 1 + block 0.5 + the abstract's 4: the nets it drives
        self.assertAlmostEqual(total["switching"], 5.5)
        # parent 1 + block 3; the abstract's declared 2 out
        self.assertAlmostEqual(total["leakage"], 4.0)
        self.assertAlmostEqual(total["total"], 24.5)
        self.assertAlmostEqual(driven["Macro"]["total"], 4.0)

    def test_macro_not_a_shard_stays_counted(self):
        sram = row(0.5, 0.25, 7.0)
        _, driven, _ = merge([parent(extra_macro=sram), block()])
        self.assertAlmostEqual(driven["Macro"]["leakage"], 7.0)
        self.assertAlmostEqual(driven["Macro"]["internal"], 0.5)
        self.assertAlmostEqual(driven["Total"]["leakage"], 11.0)

    def test_nested_unit_counted_once(self):
        top = parent()
        a = shard(
            "u_a",
            design(Sequential=row(5.0, 0.5, 3.0), Macro=row(0.2, 0.3, 0.4)),
            less=design(Sequential=row(6.0, 0.5, 3.0), Macro=row(0.2, 0.3, 0.4)),
            children=["u_rf"],
            kids=[("u_rf", 0.2, 0.3, 0.4)],
        )
        rf = shard("u_a/u_rf", design(Sequential=row(2.0, 0.1, 0.5)))
        rf["vectorless"]["design"] = design(Sequential=row(3.0, 0.1, 0.5))
        _, driven, report = merge([top, a, rf])
        self.assertAlmostEqual(driven["Total"]["internal"], 10.0 + 5.0 + 2.0)
        self.assertAlmostEqual(driven["Total"]["leakage"], 1.0 + 3.0 + 0.5)
        self.assertAlmostEqual(
            driven["Total"]["switching"], 1.0 + 4.0 + 0.5 + 0.3 + 0.1
        )
        self.assertEqual([s["unit"] for s in report["shards"]], ["", "u_a", "u_a/u_rf"])

    def test_partial_sum_without_the_parent(self):
        # a unit and its child, before the parent's shard exists: the
        # unit's scope stands where the parent's would
        a = shard(
            "u_a",
            design(Sequential=row(5.0, 0.5, 3.0), Macro=row(0.2, 0.3, 0.4)),
            less=design(Sequential=row(6.0, 0.5, 3.0), Macro=row(0.2, 0.3, 0.4)),
            children=["u_rf"],
            kids=[("u_rf", 0.2, 0.3, 0.4)],
        )
        a["child_scopes"] = ["u_rf"]
        rf = shard("u_a/u_rf", design(Sequential=row(2.0, 0.1, 0.5)))
        rf["vectorless"]["design"] = design(Sequential=row(3.0, 0.1, 0.5))
        with self.assertRaisesRegex(ValueError, "no parent shard"):
            merge([a, rf])
        _, driven, report = merge([a, rf], partial=True)
        self.assertAlmostEqual(driven["Total"]["internal"], 5.0 + 2.0)
        self.assertAlmostEqual(driven["Total"]["leakage"], 3.0 + 0.5)
        self.assertEqual([s["unit"] for s in report["shards"]], ["u_a", "u_a/u_rf"])
        # each from its own replay's SAIF: scopes side by side, not nested
        rf["scope"] = "TOP/replay_rf/dut"
        merge([a, rf], partial=True)
        # one SAIF, the child at the wrong instance below its unit: refused
        rf["scope"] = "TOP/dut/u_a/u_rf_wrong"
        with self.assertRaisesRegex(ValueError, "u_a/u_rf: read the SAIF at"):
            merge([a, rf], partial=True)

    def test_report_carries_rate_and_own_totals(self):
        _, _, report = merge([parent(), block()])
        a = report["shards"][1]
        self.assertEqual(a["unit"], "u_a")
        self.assertAlmostEqual(a["annotation"]["rate"], 0.95)
        self.assertAlmostEqual(a["vector_driven"]["total"], 8.5)
        self.assertAlmostEqual(report["shards"][0]["vector_driven"]["total"], 16.0)

    def test_unbound_saif_is_refused(self):
        wrong = block()
        wrong["vector_driven"] = wrong["vectorless"]
        with self.assertRaisesRegex(ValueError, "u_a: the SAIF-driven report equals"):
            merge([parent(), wrong])

    def test_no_annotated_pin_is_refused(self):
        with self.assertRaisesRegex(ValueError, "u_a: the SAIF annotated 0 of 20 pins"):
            merge(
                [
                    parent(),
                    shard(
                        "u_a", design(), less=design(Sequential=row(1.0)), saif_pins=0
                    ),
                ]
            )

    def test_partly_bound_scope_is_refused(self):
        # a wrong scope binding where generated names collide: the
        # reports differ, the rate gives it away
        a = block()
        a["annotation"]["saif_pins"] = 5
        with self.assertRaisesRegex(
            ValueError,
            "u_a: the SAIF annotated 5 of 20 pins at scope TOP/dut/u_a, under 90%",
        ):
            merge([parent(), a])
        merge([parent(), a], min_annotation=0.25)

    def test_child_missing_from_its_report_is_refused(self):
        p = parent()
        p["vector_driven"]["children"] = []
        with self.assertRaisesRegex(ValueError, "no power for child u_a"):
            merge([p, block()])

    def test_child_outside_macro_group_is_refused(self):
        p = parent(macro=row())
        p["vector_driven"]["children"] = [dict(row(3.0, 0.0, 0.0), name="u_a")]
        with self.assertRaisesRegex(ValueError, "Macro internal power is negative"):
            merge([p, block()])

    def test_child_scope_from_parent_odb_is_checked(self):
        top = parent(children=("core/u_a",))
        top["child_scopes"] = ["core/u_a"]
        a = block("core/u_a")
        merge([top, a])
        top["child_scopes"] = ["core__SL__u_a"]
        with self.assertRaisesRegex(
            ValueError,
            "core/u_a: read the SAIF at TOP/dut/core/u_a, but the parent's ODB "
            "has it at TOP/dut/core__SL__u_a",
        ):
            merge([top, a])

    def test_bracketed_child_matches_escaped_report_name(self):
        top = parent(children=("u_a[0]",))
        for arm in ("vectorless", "vector_driven"):
            top[arm]["children"][0]["name"] = "u_a\\[0\\]"
        a = block("u_a[0]")
        merge([top, a])

    def test_unit_twice_is_refused(self):
        with self.assertRaisesRegex(ValueError, "units reported twice: u_a"):
            merge([parent(), block(), block()])

    def test_unit_rows_prefixed_with_the_remainder(self):
        a = block()  # 5.0 internal, 0.5 switching, 3.0 leakage
        mods = [
            {
                "path": "core",
                "module": "Core",
                "depth": 1,
                "internal": 3.0,
                "switching": 0.2,
                "leakage": 2.0,
            },
            {
                "path": "core/alu",
                "module": "Alu",
                "depth": 2,
                "internal": 1.0,
                "switching": 0.1,
                "leakage": 0.5,
            },
        ]
        rows = unit_rows([a], [mods])
        self.assertEqual([r["path"] for r in rows], ["u_a", "u_a/core", "u_a/core/alu"])
        rest = rows[0]
        self.assertAlmostEqual(rest["internal"], 2.0)
        self.assertAlmostEqual(rest["leakage"], 1.0)
        depth1 = [r for r in rows if r["depth"] <= 1]
        self.assertAlmostEqual(sum(r["total"] for r in depth1), 8.5)

    def test_unit_rows_over_the_unit_refused(self):
        mods = [
            {
                "path": "core",
                "module": "Core",
                "depth": 1,
                "internal": 9.0,
                "switching": 0.0,
                "leakage": 0.0,
            }
        ]
        with self.assertRaisesRegex(
            ValueError, "u_a: its module instances' internal power"
        ):
            unit_rows([block()], [mods])

    def test_main_writes_stage_power_shape_and_fails_loudly(self):
        d = tempfile.mkdtemp()
        paths = []
        for i, s in enumerate([parent(), block()]):
            paths.append(os.path.join(d, "s{}.json".format(i)))
            with open(paths[-1], "w") as f:
                json.dump(s, f)
        outs = [os.path.join(d, n) for n in ("less.json", "driven.json", "r.json")]
        args = [
            "--vectorless",
            outs[0],
            "--vector-driven",
            outs[1],
            "--report",
            outs[2],
        ]
        self.assertEqual(main(args + paths), 0)
        with open(outs[1]) as f:
            driven = json.load(f)
        self.assertEqual(sorted(driven), sorted(GROUPS))
        self.assertEqual(
            sorted(driven["Total"]), ["internal", "leakage", "switching", "total"]
        )

        wrong = block()
        wrong["vector_driven"] = wrong["vectorless"]
        with open(paths[1], "w") as f:
            json.dump(wrong, f)
        self.assertEqual(main(args + paths), 1)


if __name__ == "__main__":
    unittest.main()
