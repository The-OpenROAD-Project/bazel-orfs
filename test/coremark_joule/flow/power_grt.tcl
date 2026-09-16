# SAIF-driven report_power at a pre-route stage.
#
# Unlike the post-route power flow, there is no SPEF to read: parasitics
# at global route come from `estimate_parasitics -global_routing`, which
# is what makes a grt-stage energy number possible at all and is the
# whole reason this study screens here rather than after detailed route.
#
# Two passes are run and both are written out:
#
#   vectorless      clock activity only, OpenSTA's default assumptions
#   vector-driven   the SAIF's measured toggle activity
#
# Keeping both is a check, not a courtesy. If the SAIF fails to bind --
# wrong scope, mismatched net names, a capture from another stage --
# OpenSTA does not fail. It falls back to default activity, and the two
# reports come out identical. Comparing them is how that shows up.
#
# Required env:
#   STAGE_STEM              ORFS stage stem, e.g. 5_1_grt
#   SAIF_STIMULI            path to the .saif
#   SAIF_SCOPE              hierarchy in the SAIF that corresponds to the
#                           linked design root, e.g. TOP/cm_soc/cpu
#   VECTORLESS_POWER_JSON   output path, clock-only pass
#   VECTOR_DRIVEN_POWER_JSON output path, SAIF-annotated pass

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

log_cmd estimate_parasitics -global_routing

log_cmd report_power
report_power -format json > $::env(VECTORLESS_POWER_JSON)

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

log_cmd report_power
report_power -format json > $::env(VECTOR_DRIVEN_POWER_JSON)
