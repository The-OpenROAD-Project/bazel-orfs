"""A stage's exec_properties are its own, the other stages keep the flow's.

orfs_flow(exec_properties = ...) gives every stage target the same
dictionary, so a flow whose global route needs a large remote worker
reserved one for synthesis and placement too. stage_exec_properties
names the stages that differ.

The test reads the stage targets orfs_flow declared and compares their
exec_properties with what the BUILD file expects: nothing is built, so
the properties need not name a platform any executor has.
"""

load("@bazel_skylib//rules:diff_test.bzl", "diff_test")
load("@bazel_skylib//rules:write_file.bzl", "write_file")

def stage_exec_properties_test(name, expected):
    """Compares the exec_properties of targets of this package with expected.

    Args:
      name: name of the test.
      expected: dictionary from a target's name to its exec_properties.
    """
    actual = {}
    for target in expected:
        rule = native.existing_rule(target)
        if rule == None:
            fail("{}: no target {} in this package".format(name, target))
        actual[target] = dict(rule.get("exec_properties") or {})
    for kind, content in [("expected", expected), ("actual", actual)]:
        write_file(
            name = "{}_{}".format(name, kind),
            out = "{}_{}.json".format(name, kind),
            content = [json.encode_indent(
                {target: {k: content[target][k] for k in sorted(content[target])} for target in sorted(content)},
            )],
        )
    diff_test(
        name = name,
        file1 = ":{}_expected".format(name),
        file2 = ":{}_actual".format(name),
    )
