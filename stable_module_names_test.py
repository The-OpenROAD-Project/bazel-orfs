import json
import os
import tempfile
import unittest

import stable_module_names as s


def leaf(name, width=8):
    return (
        f"module {name}(input clock, input [{width - 1}:0] d, "
        f"output [{width - 1}:0] q);\n  assign q = d;\nendmodule\n"
    )


def parent(name, *instances):
    body = "".join(
        f"  {child} {inst} (\n    .clock (clock),\n    .d (d),\n    .q ()\n  );\n"
        for child, inst in instances
    )
    return f"module {name}(input clock, input [7:0] d);\n{body}endmodule\n"


def modules(sources):
    found, _ = s.parse(sources)
    return {name: m.text for name, m in found.items()}


class FamiliesTest(unittest.TestCase):
    def test_numbered_names_form_one_family(self):
        self.assertEqual(
            s.families(["Q", "Q_1", "Q_2", "R", "S_3"]),
            {"Q": "Q", "Q_1": "Q", "Q_2": "Q"},
        )

    def test_groups_decide_the_family(self):
        groups = {"Q": "Q", "Q_1": "Q", "Adder_8": "Adder_8", "Adder_16": "Adder_16"}
        self.assertEqual(
            s.families(["Q", "Q_1", "Adder_8", "Adder_16", "Blackbox"], groups),
            {"Q": "Q", "Q_1": "Q"},
        )


class ParseTest(unittest.TestCase):
    def test_instances_with_parameters_ranges_and_comments(self):
        text = (
            "// module Fake;\n"
            "module Top(input clock);\n"
            "  /* Child not_an_instance ( */\n"
            "  Child #(.W(8), .D((2))) a (.clock(clock));\n"
            "  Child b [3:0] (.clock(clock));\n"
            "  Macro m (.clock(clock));\n"
            '  initial $display("Child c (");\n'
            "endmodule\n" + leaf("Child")
        )
        found, _ = s.parse([("t.sv", text)])
        self.assertEqual(sorted(found), ["Child", "Top"])
        self.assertEqual(
            [(c, i) for c, i, _ in found["Top"].instances],
            [("Child", "a"), ("Child", "b")],
        )

    def test_a_module_defined_twice_stops(self):
        with self.assertRaisesRegex(s.StableNamesError, "defined in both"):
            s.parse([("a.sv", leaf("Q")), ("b.sv", leaf("Q"))])


class RenameTest(unittest.TestCase):
    def test_contested_modules_take_their_path(self):
        sources = [
            (
                "d.sv",
                leaf("Q")
                + leaf("Q_1", 16)
                + leaf("Unique")
                + parent("A", ("Q", "q"), ("Unique", "u"))
                + parent("B", ("Q_1", "q"))
                + parent("Top", ("A", "a"), ("B", "b")),
            )
        ]
        out, mapping = s.rename(sources, "Top")
        self.assertEqual(mapping, {"Q": ["Q__A__q"], "Q_1": ["Q__B__q"]})
        found = modules(out)
        self.assertEqual(
            sorted(found), ["A", "B", "Q__A__q", "Q__B__q", "Top", "Unique"]
        )
        self.assertIn("  Q__A__q q (", found["A"])
        self.assertIn("  Unique u (", found["A"])
        self.assertIn("[15:0]", found["Q__B__q"])

    def test_a_contested_module_under_two_parents_is_cloned(self):
        sources = [
            (
                "d.sv",
                leaf("Q")
                + leaf("Q_1", 16)
                + parent("A", ("Q", "q"))
                + parent("B", ("Q", "z"), ("Q", "y"), ("Q_1", "w"))
                + parent("Top", ("A", "a"), ("B", "b")),
            )
        ]
        out, mapping = s.rename(sources, "Top")
        self.assertEqual(mapping["Q"], ["Q__A__q", "Q__B__y"])
        found = modules(out)
        self.assertEqual(found["B"].count("Q__B__y "), 2)

    def test_a_parents_new_name_feeds_its_childrens(self):
        sources = [
            (
                "d.sv",
                leaf("L")
                + leaf("L_1", 16)
                + parent("P", ("L", "l"))
                + parent("P_1", ("L_1", "l"))
                + parent("Top", ("P", "p0"), ("P_1", "p1")),
            )
        ]
        _, mapping = s.rename(sources, "Top")
        self.assertEqual(
            mapping,
            {
                "L": ["L__P__Top__p0__l"],
                "L_1": ["L__P__Top__p1__l"],
                "P": ["P__Top__p0"],
                "P_1": ["P__Top__p1"],
            },
        )

    def test_excluded_and_undefined_modules_keep_their_names(self):
        sources = [
            (
                "d.sv",
                leaf("mem_1")
                + leaf("mem_2", 16)
                + parent("Top", ("mem_1", "a"), ("mem_2", "b"), ("Macro_1", "m")),
            )
        ]
        out, mapping = s.rename(sources, "Top", exclude=["mem_*"])
        self.assertEqual(mapping, {})
        self.assertEqual(out, sources)

    def test_unreached_modules_are_dropped_and_text_between_kept(self):
        sources = [
            ("a.sv", "`ifndef X\n`define X\n`endif\n" + leaf("Q") + leaf("Q_1")),
            ("b.sv", "// b\n" + leaf("Dead") + parent("Top", ("Q", "q"))),
        ]
        out, _ = s.rename(sources, "Top")
        self.assertTrue(out[0][1].startswith("`ifndef X\n`define X\n`endif\n"))
        self.assertNotIn("Q_1", out[0][1])
        self.assertNotIn("Dead", out[1][1])
        self.assertTrue(out[1][1].startswith("// b\n"))

    def test_long_names_hash_the_parent(self):
        long_parent = "P" * 120
        sources = [
            (
                "d.sv",
                leaf("Q")
                + leaf("Q_1", 16)
                + parent(long_parent, ("Q", "q"), ("Q_1", "r"))
                + parent("Top", (long_parent, "p")),
            )
        ]
        _, mapping = s.rename(sources, "Top")
        for new in mapping["Q"] + mapping["Q_1"]:
            self.assertLessEqual(len(new), s.MAX_NAME_LENGTH)
        self.assertRegex(mapping["Q"][0], r"^Q__[0-9a-f]{12}__q$")

    def test_a_new_name_taken_by_a_module_stops(self):
        sources = [
            (
                "d.sv",
                leaf("Q")
                + leaf("Q_1")
                + leaf("Q__Top__q")
                + parent("Top", ("Q", "q"), ("Q_1", "r"), ("Q__Top__q", "x")),
            )
        ]
        with self.assertRaisesRegex(s.StableNamesError, "already a module"):
            s.rename(sources, "Top")

    def test_bind_to_a_renamed_module_stops(self):
        sources = [
            (
                "d.sv",
                leaf("Q")
                + leaf("Q_1")
                + parent("Top", ("Q", "q"), ("Q_1", "r"))
                + "bind Q Checker c (.clock(clock));\n",
            )
        ]
        with self.assertRaisesRegex(s.StableNamesError, "bind"):
            s.rename(sources, "Top")

    def test_missing_top_stops(self):
        with self.assertRaisesRegex(s.StableNamesError, "top module"):
            s.rename([("d.sv", leaf("Q"))], "Top")


class KeptTest(unittest.TestCase):
    def test_kept_names_are_checked_against_the_output(self):
        sources = [("d.sv", leaf("Q__Top__q") + parent("Top", ("Q__Top__q", "q")))]
        self.assertEqual(
            s.check_kept(
                ["Top", "Q__Top__q", "Q", "Gone"],
                sources,
                {"Q": ["Q__Top__q"]},
            ),
            ["Q: renamed to Q__Top__q", "Gone: no such module"],
        )

    def test_retime_patterns_renaming_broke_are_reported(self):
        sources = [("d.sv", leaf("Q__Top__q") + parent("Top", ("Q__Top__q", "q")))]
        self.assertEqual(
            s.check_kept(
                ["Top", "R"], sources, {"Q": ["Q__Top__q"]}, ["Q*", "Q", "Gone*"]
            ),
            ["R: no such module", "Q: renamed to Q__Top__q"],
        )


class EditTest(unittest.TestCase):
    """An instance added to one module renames nothing outside it."""

    def test_an_added_instance_changes_only_its_parent(self):
        here = os.path.join(os.path.dirname(__file__), "test", "stable_module_names")
        designs = {}
        for name in ("before", "after"):
            sources = s.read_sources([os.path.join(here, name + ".sv")])
            raw = modules(sources)
            out, _ = s.rename(sources, "top")
            designs[name] = (raw, modules(out))
        (raw_before, before), (raw_after, after) = designs["before"], designs["after"]

        raw_changed = {n for n in raw_before if raw_after.get(n) != raw_before[n]}
        self.assertEqual(raw_changed, {"Queue_1", "Queue_2", "Mul", "Div"})

        self.assertEqual(set(after) - set(before), {"Queue__Mul__extraQueue"})
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual({n for n in before if after[n] != before[n]}, {"Mul"})


class MainTest(unittest.TestCase):
    def test_output_is_byte_stable_and_kept_names_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "rtl")
            os.makedirs(src)
            with open(os.path.join(src, "b.sv"), "w") as f:
                f.write(parent("Top", ("Q", "q"), ("Q_1", "r")))
            with open(os.path.join(src, "a.sv"), "w") as f:
                f.write(leaf("Q") + leaf("Q_1", 16))
            groups = os.path.join(tmp, "groups.json")
            with open(groups, "w") as f:
                json.dump({"Q": "Q", "Q_1": "Q", "Top": "Top"}, f)
            outputs = []
            for i in range(2):
                out = os.path.join(tmp, f"out{i}.sv")
                names = os.path.join(tmp, f"names{i}.json")
                rc = s.main(
                    ["--top", "Top", "--out", out, "--map", names]
                    + ["--groups", groups, "--keep", "Q__Top__q", src]
                )
                self.assertEqual(rc, 0)
                with open(out) as f, open(names) as g:
                    outputs.append((f.read(), g.read()))
            self.assertEqual(outputs[0], outputs[1])
            self.assertLess(
                outputs[0][0].index("// a.sv"), outputs[0][0].index("// b.sv")
            )
            self.assertEqual(
                json.loads(outputs[0][1]), {"Q": ["Q__Top__q"], "Q_1": ["Q__Top__r"]}
            )
            rc = s.main(
                ["--top", "Top", "--out", out, "--map", names, "--keep", "Q_1", src]
            )
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
