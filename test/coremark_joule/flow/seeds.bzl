"""Placement-seed variants of a design, from the design's own parsed config.

§5.11: every point was one flow run at one placement seed, so no number
had an error bar. The stage-variance study found this flow's run-to-run
noise is born at placement, so the ensemble varies the global placer's
seed and nothing else: each variant starts from the design's own
floorplan (previous_stage), so synthesis and floorplan are shared
byte-for-byte and only placement onward differs. The design's own draw
is sample one -- global_placement's default -random_seed is 1, and
VeeR's config.mk pins 2 -- so SEEDS start where no design's own seed can
be, and are the other four.

Declared through design()'s `extra` hook, so a variant can never
disagree with the design it measures: the arguments, sources and
verilog files are the ones the parser produced for config.mk.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "stage_power")

SEEDS = [
    11,
    12,
    13,
    14,
]

def seed_variants(saif_prefix, saif_scope, max_renames = 0):
    """Return design()'s `extra` callable for one core.

    Args:
      saif_prefix: label prefix of the core's SAIF captures in //sim, e.g.
        "//test/coremark_joule/sim:ibex_rv32imc"; seed n reads
        "<prefix>_seed<n>_saif".
      saif_scope: as stage_power().
      max_renames: as grt_netlist(); VeeR's known collision budget.
    """

    def extra(name, platform, verilog_files, arguments, user_arguments, sources, user_sources, user_stages, macros, stage_data, tags):
        for seed in SEEDS:
            # variant, not a new name: the flow's outputs land under
            # results/<platform>/<design>/seed<n>/ rather than colliding
            # with the design's own base/ files, and its targets are
            # <design>_seed<n>_<stage>.
            variant = "{}_seed{}".format(name, seed)
            orfs_flow(
                name = name,
                variant = "seed{}".format(seed),
                top = name,
                verilog_files = verilog_files,
                macros = macros,
                sources = sources,
                user_sources = user_sources,
                user_stages = user_stages,
                arguments = arguments | {"GPL_RANDOM_SEED": str(seed)},
                user_arguments = user_arguments,
                stage_data = stage_data,
                previous_stage = {"place": ":{}_floorplan".format(name)},
                last_stage = "grt",
                tags = ["manual"],
                visibility = ["//test/coremark_joule:__subpackages__"],
            )
            grt_netlist(
                name = variant + "_grt_netlist",
                src = ":" + variant + "_grt",
                max_renames = max_renames,
                visibility = ["//test/coremark_joule:__subpackages__"],
            )
            stage_power(
                name = variant + "_grt_power",
                src = ":" + variant + "_grt",
                saif = "{}_seed{}_saif".format(saif_prefix, seed),
                saif_scope = saif_scope,
                visibility = ["//test/coremark_joule:__subpackages__"],
            )

    return extra
