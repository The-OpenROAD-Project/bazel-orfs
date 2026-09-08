"""Unit tests for the BUILD file the pinner writes.

build_write() used to be a match/case statement, which made pin.py a
Python 3.10 file executed by whatever `python3` the host has -- a
SyntaxError on RHEL 8 (3.6), SLES 15 (3.6) and Ubuntu 20.04 (3.8).  These
tests nail down the output of both branches so the rewrite can be checked
against what the match statement emitted.
"""

import io
import unittest

import pin


def artifact(name, paths, package="pinned"):
    return pin.Artifact(
        label=pin.Label(repo="", package=package, name=name),
        files=frozenset(
            pin.File(
                path="bazel-out/k8-fastbuild/bin/" + p,
                root="bazel-out/k8-fastbuild/bin",
                workspace_root="",
            )
            for p in paths
        ),
    )


def build_file(*artifacts):
    out = io.StringIO()
    pin.build_write(list(artifacts), out)
    return out.getvalue()


class BuildWriteTest(unittest.TestCase):
    def test_single_file_named_after_label_exports_the_file(self):
        # One file whose archive path is the label name: the label has to
        # keep naming the file itself, so it is re-exported rather than
        # wrapped in a group.
        self.assertEqual(
            build_file(artifact("6_final.gds", ["pinned/6_final.gds"])),
            "exports_files(\n"
            "  srcs = [\n"
            "    '6_final.gds',\n"
            "  ],\n"
            '  visibility = ["//visibility:public"],\n'
            ")\n",
        )

    def test_several_files_become_a_filegroup(self):
        self.assertEqual(
            build_file(artifact("results", ["pinned/a.def", "pinned/b.odb"])),
            "filegroup(\n"
            "  name = 'results',\n"
            "  srcs = [\n"
            "    'a.def',\n"
            "    'b.odb',\n"
            "  ],\n"
            '  visibility = ["//visibility:public"],\n'
            ")\n",
        )

    def test_single_file_not_named_after_label_becomes_a_filegroup(self):
        self.assertEqual(
            build_file(artifact("netlist", ["pinned/6_final.v"])),
            "filegroup(\n"
            "  name = 'netlist',\n"
            "  srcs = [\n"
            "    '6_final.v',\n"
            "  ],\n"
            '  visibility = ["//visibility:public"],\n'
            ")\n",
        )

    def test_srcs_are_sorted_so_the_generated_file_is_stable(self):
        forward = build_file(artifact("r", ["pinned/a.def", "pinned/b.odb"]))
        reverse = build_file(artifact("r", ["pinned/b.odb", "pinned/a.def"]))
        self.assertEqual(forward, reverse)

    def test_every_artifact_gets_its_own_block(self):
        text = build_file(
            artifact("6_final.gds", ["pinned/6_final.gds"]),
            artifact("results", ["pinned/a.def", "pinned/b.odb"]),
        )
        self.assertEqual(text.count("exports_files("), 1)
        self.assertEqual(text.count("filegroup("), 1)


if __name__ == "__main__":
    unittest.main()
