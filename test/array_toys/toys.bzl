"""The array toys, one flow per kind, depth and width, per arm."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@bazel_skylib//rules:write_file.bzl", "write_file")

# generate_ram's register file: the kinds it can build today, and their
# spec's ports
_REGFILE_PORTS = {
    "rf1r1w": (["r0"], ["w0"]),
    "rf4r2w": (["r0", "r1", "r2", "r3"], ["w0", "w1"]),
}

_CELLS = """\
cell flop DFFHQNx1_ASAP7_75t_R
cell and2 AND2x2_ASAP7_75t_R
cell or2 OR2x2_ASAP7_75t_R
cell ao22 AO22x2_ASAP7_75t_R
cell inv INVx1_ASAP7_75t_R
cell tap TAPCELL_ASAP7_75t_R
pin_layer M4
"""

def _spec(depth, width, reads, writes):
    lines = ["module Arr", "words %d" % depth, "bits %d" % width, "clock clock"]
    lines += ["read %s_addr %s_data" % (r, r) for r in reads]
    lines += ["write %s_addr %s_data %s_en" % (w, w, w) for w in writes]
    return "\n".join(lines) + "\n" + _CELLS

def array_toy(kind, depth, width):
    """A toy, synthesised by yosys and, where it can, generated.

    Args:
      kind: a kind in toys.py.
      depth: words.
      width: bits per word.
    """
    name = "%s_%dx%d" % (kind, depth, width)
    arms = [("yosys", {})]
    if kind in _REGFILE_PORTS:
        reads, writes = _REGFILE_PORTS[kind]
        write_file(
            name = name + "_spec",
            out = name + ".regfile",
            content = [_spec(depth, width, reads, writes)],
            tags = ["manual"],
        )
        arms.append(("generate_ram", {"AUTO_MEMORIES_REGFILES": [":" + name + ".regfile"]}))
    for arm, sources in arms:
        flow = "%s_%s" % (name, arm)

        # the top is named after the flow: a flow's results are keyed on it
        native.genrule(
            name = flow + "_rtl",
            outs = [flow + ".sv"],
            cmd = "$(execpath :toys) %s %d %d $@ %s" % (kind, depth, width, flow),
            tools = [":toys"],
            tags = ["manual"],
        )
        orfs_flow(
            name = flow,
            arguments = {
                "AUTO_MEMORIES": "1",
                "CORE_UTILIZATION": "30",
                "PLACE_DENSITY": "0.5",
                "SYNTH_HDL_FRONTEND": "slang",
            },
            last_stage = "floorplan",
            sources = {"SDC_FILE": [":constraint.sdc"]} | sources,
            tags = ["manual"],
            verilog_files = [":" + flow + ".sv"],
        )
        orfs_run(
            name = flow + "_period",
            src = ":" + flow + "_floorplan",
            outs = [flow + "_period.json"],
            script = ":period_probe.tcl",
            tags = ["manual"],
            user_arguments = {
                "OUTPUT_JSON": "$(location %s_period.json)" % flow,
            },
        )
