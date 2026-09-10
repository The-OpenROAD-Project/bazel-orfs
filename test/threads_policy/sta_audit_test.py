#!/usr/bin/env python3
"""The audit is a regular-expression scan of C++, so its parser is tested.

Every fixture here is a shape that actually occurs in the OpenSTA the
flow builds -- a multi-line template argument list, an alias with an
explicit id-based hash, a bare local inside a parallel visitor -- because
a scan that silently skips a shape reports fewer risky sites than exist,
which is the one wrong answer this audit must not give.
"""

import unittest

import sta_audit

MODULE_SNIPPET = """
archive_override(
    module_name = "openroad",
    patch_cmds = [
        "curl -o .openroad-submodule-src-sta-65bd9df5f7846015313734d08a5a6367df79453c.tar.gz https://example/x && echo 'c2c47d7540d49c458bca977e9145eb129f97e33212deb2c27803a92ddaf6fae0  .openroad-submodule-src-sta-65bd9df5f7846015313734d08a5a6367df79453c.tar.gz' | sha256sum -c -",
    ],
)
"""


class Pinning(unittest.TestCase):
    def test_commit_is_parsed_from_the_override(self):
        self.assertEqual(
            sta_audit.pinned_sta_commit(MODULE_SNIPPET),
            "65bd9df5f7846015313734d08a5a6367df79453c",
        )

    def test_sha256_is_parsed_beside_it(self):
        self.assertEqual(
            sta_audit.pinned_sta_sha256(
                MODULE_SNIPPET, "65bd9df5f7846015313734d08a5a6367df79453c"
            ),
            "c2c47d7540d49c458bca977e9145eb129f97e33212deb2c27803a92ddaf6fae0",
        )

    def test_a_missing_submodule_line_is_an_error_not_a_default(self):
        with self.assertRaises(SystemExit):
            sta_audit.pinned_sta_commit("archive_override(patch_cmds = [])")

    def test_two_commits_is_an_error(self):
        with self.assertRaises(SystemExit):
            sta_audit.pinned_sta_commit(
                MODULE_SNIPPET + ".openroad-submodule-src-sta-" + "a" * 40 + ".tar.gz"
            )


class Arguments(unittest.TestCase):
    def test_nested_template_commas_are_not_argument_separators(self):
        self.assertEqual(
            sta_audit.split_args("const Pin*, std::pair<int, int>, PinIdHash"),
            ["const Pin*", "std::pair<int, int>", "PinIdHash"],
        )

    def test_pointer_key_survives_const(self):
        self.assertEqual(sta_audit.key_kind("const Pin*"), "pointer")
        self.assertEqual(sta_audit.key_kind("Vertex *"), "pointer")

    def test_value_key(self):
        self.assertEqual(sta_audit.key_kind("unsigned"), "value")
        self.assertEqual(sta_audit.key_kind("std::string"), "value")
        self.assertEqual(sta_audit.key_kind("SeqPin"), "value")

    def test_map_hash_is_the_third_argument_set_hash_the_second(self):
        self.assertEqual(
            sta_audit.hash_kind(
                "unordered_map", ["const Pin*", "ClockSet*", "PinIdHash"]
            ),
            "PinIdHash",
        )
        self.assertEqual(
            sta_audit.hash_kind("unordered_set", ["Tag*", "TagHash", "TagEqual"]),
            "TagHash",
        )

    def test_a_defaulted_hash_is_named_so_the_table_cannot_read_as_blank(self):
        self.assertEqual(
            sta_audit.hash_kind("unordered_map", ["const Pin*", "LogicValue"]),
            "std::hash",
        )


class Declarations(unittest.TestCase):
    def test_alias_declaration(self):
        text = "using SimValueMap = std::unordered_map<const Pin*, LogicValue>;\n"
        sites = sta_audit.find_sites("search/Sim.hh", text)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].names, ["SimValueMap"])
        self.assertEqual(sites[0].key, "pointer")
        self.assertEqual(sites[0].hash, "std::hash")
        self.assertEqual(sites[0].line, 1)

    def test_template_arguments_wrapped_across_lines(self):
        # The shape of Sdc.hh's EdgeExceptionsMap and Power.hh's
        # PwrSeqActivityMap: the closing bracket is on the next line.
        text = (
            "using PwrSeqActivityMap = std::unordered_map<SeqPin, PwrActivity,\n"
            "                                             SeqPinHash, SeqPinEqual>;\n"
        )
        sites = sta_audit.find_sites("power/Power.hh", text)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].key, "value")
        self.assertEqual(sites[0].hash, "SeqPinHash")

    def test_bare_local_declaration_takes_its_variable_name(self):
        # ClkSkew.cc's `visited` set, declared inside a parallel walk.
        text = "  std::unordered_set<Vertex *> visited;\n"
        sites = sta_audit.find_sites("search/ClkSkew.cc", text)
        self.assertEqual(sites[0].names, ["visited"])
        self.assertEqual(sites[0].key, "pointer")

    def test_a_comment_is_not_a_declaration(self):
        text = "// 2. Maps (map<K, T*>, unordered_map<K, T*>)\n"
        self.assertEqual(
            sta_audit.find_sites("include/sta/ContainerHelpers.hh", text), []
        )

    def test_unbalanced_brackets_are_skipped_rather_than_guessed(self):
        text = "if (a < unordered_map_count && b > c) {\n"
        self.assertEqual(sta_audit.find_sites("x.cc", text), [])


class Iteration(unittest.TestCase):
    def test_range_for_over_the_variable_is_evidence(self):
        texts = {"search/Sim.cc": "  for (auto [pin, value] : value_map_) {\n"}
        self.assertEqual(
            sta_audit.iteration_evidence(texts, "value_map_"), "search/Sim.cc:1"
        )

    def test_begin_is_evidence(self):
        texts = {"a.cc": "\n\n  auto it = value_map_.begin();\n"}
        self.assertEqual(sta_audit.iteration_evidence(texts, "value_map_"), "a.cc:3")

    def test_lookup_only_is_not_evidence(self):
        texts = {"a.cc": "  auto it = value_map_.find(pin);\n"}
        self.assertIsNone(sta_audit.iteration_evidence(texts, "value_map_"))

    def test_scope_confines_the_search_to_one_file(self):
        texts = {"a.cc": "for (auto v : visited) {}\n", "b.cc": "visited.insert(x);\n"}
        self.assertEqual(sta_audit.iteration_evidence(texts, "visited"), "a.cc:1")
        self.assertIsNone(sta_audit.iteration_evidence(texts, "visited", "b.cc"))

    def test_a_scoped_search_starts_at_the_declaration(self):
        # network/NetworkCmp.cc declares four parameters named `set`;
        # the first one in the file belongs to a different function.
        text = (
            "for (const Port *p : *set)\n"
            "sortByPathName(const PinUnorderedSet *set)\n"
            "for (const Pin *pin : *set)\n"
        )
        texts = {"network/NetworkCmp.cc": text}
        self.assertEqual(
            sta_audit.iteration_evidence(texts, "set", "network/NetworkCmp.cc", 1),
            "network/NetworkCmp.cc:3",
        )

    def test_a_member_is_named_by_its_trailing_underscore(self):
        self.assertTrue(sta_audit.is_member("sim_value_map_"))
        self.assertFalse(sta_audit.is_member("visited"))
        self.assertFalse(sta_audit.is_member("set"))

    def test_an_alias_is_resolved_through_the_variable_declared_with_it(self):
        header = "using SimValueMap = std::unordered_map<const Pin*, LogicValue>;\n"
        body = "SimValueMap value_map_;\nfor (auto p : value_map_) {}\n"
        texts = {"search/Sim.hh": header, "search/Sim.cc": body}
        sites = sta_audit.resolve_iteration(
            sta_audit.find_sites("search/Sim.hh", header), texts
        )
        self.assertTrue(sites[0].iterated)
        self.assertIn("value_map_", sites[0].evidence)
        self.assertIn("search/Sim.cc:2", sites[0].evidence)

    def test_a_local_is_not_matched_against_a_namesake_in_another_file(self):
        # The real false positive: ClkSkew.cc's `visited` is only
        # inserted into, and Sta.cc iterates a VertexSet of the same
        # name. Scoping a local to its own file is what separates them.
        clkskew = "  std::unordered_set<Vertex *> visited;\n  visited.insert(v);\n"
        sta = "  VertexSet visited = makeVertexSet(this);\n  for (Vertex *v : visited) {}\n"
        texts = {"search/ClkSkew.cc": clkskew, "search/Sta.cc": sta}
        sites = sta_audit.resolve_iteration(
            sta_audit.find_sites("search/ClkSkew.cc", clkskew), texts
        )
        self.assertFalse(sites[0].iterated)
        self.assertEqual(sta_audit.risk(sites[0]), "latent")

    def test_a_parameter_is_not_matched_against_a_namesake_either(self):
        # The second false positive: PinUnorderedSet is only ever a
        # parameter named `set`, and `liberty/Liberty.cc` iterates a
        # LibertyPortSet parameter of the same name.
        header = "using PinUnorderedSet = std::unordered_set<const Pin*>;\n"
        cmp_cc = (
            "sortByPathName(const PinUnorderedSet *set,\n  const Network *n)\n{\n}\n"
        )
        liberty = (
            "sortByName(const LibertyPortSet *set)\n{\n  for (LibertyPort *p : *set)\n"
        )
        texts = {
            "include/sta/NetworkClass.hh": header,
            "network/NetworkCmp.cc": cmp_cc,
            "liberty/Liberty.cc": liberty,
        }
        sites = sta_audit.resolve_iteration(
            sta_audit.find_sites("include/sta/NetworkClass.hh", header), texts
        )
        self.assertFalse(sites[0].iterated)

    def test_variables_of_reports_where_each_declaration_is(self):
        texts = {"power/Power.hh": "  PwrActivityMap user_activity_map_;\n"}
        self.assertEqual(
            sta_audit.variables_of(texts, "PwrActivityMap"),
            [("power/Power.hh", 1, "user_activity_map_")],
        )


class Risk(unittest.TestCase):
    def _site(self, **kwargs):
        base = dict(
            path="a.hh",
            line=1,
            container="unordered_map",
            key="pointer",
            key_type="const Pin*",
            hash="std::hash",
            names=["M"],
            iterated=False,
            evidence=None,
            decl="d",
        )
        base.update(kwargs)
        return sta_audit.Site(**base)

    def test_address_hashed_and_iterated_is_a_shortlist_entry(self):
        # Named "iterated" and not "high": iteration in bucket order is
        # only a bug when the order survives the loop body, which no
        # regular expression can decide.
        self.assertEqual(
            sta_audit.risk(self._site(iterated=True, evidence="a.cc:1")), "iterated"
        )

    def test_the_table_says_iterated_is_not_a_defect_count(self):
        out = sta_audit.markdown(
            [self._site(iterated=True, evidence="a.cc:1")], "a" * 40
        )
        self.assertIn("not a defect count", out)

    def test_address_hashed_without_observed_iteration_is_latent_not_low(self):
        self.assertEqual(sta_audit.risk(self._site()), "latent")

    def test_value_key_is_low(self):
        self.assertEqual(sta_audit.risk(self._site(key="value")), "low")

    def test_a_named_hash_is_low_and_the_name_is_carried_for_reading(self):
        site = self._site(hash="PinIdHash", iterated=True, evidence="a.cc:1")
        self.assertEqual(sta_audit.risk(site), "low")
        self.assertIn("PinIdHash", sta_audit.markdown([site], "abc123"))


class Sources(unittest.TestCase):
    def test_test_and_example_trees_are_not_the_tool(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            for rel in ("search/Sim.hh", "test/Fixture.cc", "examples/e.cc"):
                os.makedirs(os.path.join(root, os.path.dirname(rel)), exist_ok=True)
                open(os.path.join(root, rel), "w").close()
            self.assertEqual(sta_audit.tool_sources(root), ["search/Sim.hh"])


class Rendering(unittest.TestCase):
    def test_a_commit_is_abbreviated_but_a_path_is_not(self):
        self.assertEqual(sta_audit.heading_label("a" * 40), "aaaaaaaaaa")
        self.assertEqual(
            sta_audit.heading_label("unpinned tree /some/where"),
            "unpinned tree /some/where",
        )

    def test_an_unpinned_tree_is_named_as_such_in_the_heading(self):
        text = "using M = std::unordered_map<const Pin*, int>;\n"
        sites = sta_audit.find_sites("a.hh", text)
        out = sta_audit.markdown(sites, "unpinned tree /somewhere")
        self.assertIn("unpinned tree", out)

    def test_a_pipe_in_a_declaration_cannot_break_the_table(self):
        site = sta_audit.Site(
            path="a.hh",
            line=1,
            container="unordered_map",
            key="pointer",
            key_type="const Pin*",
            hash="std::hash",
            names=["M"],
            iterated=False,
            evidence=None,
            decl="using M = std::unordered_map<A|B, int>",
        )
        row = [
            line
            for line in sta_audit.markdown([site], "abc").splitlines()
            if line.startswith("| latent")
        ][0]
        self.assertEqual(row.count("|"), 7 + 1)


if __name__ == "__main__":
    unittest.main()
