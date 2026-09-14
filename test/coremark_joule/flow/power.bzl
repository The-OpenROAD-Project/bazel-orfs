"""Turning a placed-and-routed stage into an energy number.

The chain, and why each link is where it is:

  grt_netlist     the stage's ODB written out as Verilog, because the
                  gate-level simulation needs a netlist and the flow
                  writes only an ODB at a stage boundary.

The netlist must come from the same stage the power is reported on. A
SAIF captured against one stage's netlist and applied to another leaves
nets unmatched, and OpenSTA falls back to default activity for them
rather than failing -- so the error shows up as a plausible number.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_run")

# ORFS stage stems, as private/stages.bzl spells them. The netlist and
# the power report have to name the same one.
STAGE_STEM = {
    "cts": "4_1_cts",
    "grt": "5_1_grt",
    "route": "5_route",
    "final": "6_final",
}

def grt_netlist(name, src, stage = "grt", out = None, tags = ["manual"], visibility = None):
    """Write a stage's gate-level netlist from its ODB.

    Args:
      name: target name.
      src: the flow stage target whose ODB is read.
      stage: which stage's files to load; must match `src`.
      out: output filename; defaults to `<name>.v`.
      tags: forwarded; manual, since this needs the flow to have run.
      visibility: forwarded.
    """
    out = out or (name + ".v")
    orfs_run(
        name = name,
        src = src,
        outs = [out],
        script = "//test/coremark_joule/flow:write_netlist.tcl",
        user_arguments = {
            "OUTPUT": "$(location {})".format(out),
            "STAGE_STEM": STAGE_STEM[stage],
        },
        tags = tags,
        visibility = visibility,
    )
