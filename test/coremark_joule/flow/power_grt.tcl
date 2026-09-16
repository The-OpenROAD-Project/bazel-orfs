# SAIF-driven report_power, at global route or after detailed route.
#
# Parasitics come from whichever source the stage has. At global route
# there is no SPEF, so `estimate_parasitics -global_routing` predicts
# them from the global routes -- which is what makes a grt-stage energy
# number possible at all and is why this study screens there rather than
# after detailed route. After detailed route the parasitics are
# extracted rather than predicted, and POWER_SPEF names the file.
#
# Reading a SPEF is not the same measurement as estimating: it is the
# calibration of the estimate. 5.3 of the paper reports the delta on one
# design, which is what says how much the screening choice costs.
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
#   POWER_SPEF              optional; a .spef to read instead of
#                           estimating. Set it only for a stage that has
#                           one -- reading a SPEF written for a different
#                           netlist annotates nothing and says so only in
#                           the log.
#   SAIF_STIMULI            path to the .saif
#   SAIF_SCOPE              hierarchy in the SAIF that corresponds to the
#                           linked design root, e.g. TOP/cm_soc/cpu
#   VECTORLESS_POWER_JSON   output path, clock-only pass
#   VECTOR_DRIVEN_POWER_JSON output path, SAIF-annotated pass

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

if { [info exists ::env(POWER_SPEF)] && $::env(POWER_SPEF) ne "" } {
    # A bare name is resolved against RESULTS_DIR, where the flow writes
    # it. Missing is an error rather than a fallback to estimating: a
    # silent fallback would report an estimate under a target whose whole
    # purpose is to not be one.
    set spef $::env(POWER_SPEF)
    if { ![file exists $spef] } {
        set spef [file join $::env(RESULTS_DIR) $::env(POWER_SPEF)]
    }
    if { ![file exists $spef] } {
        error "POWER_SPEF set to '$::env(POWER_SPEF)' but no such file"
    }
    log_cmd read_spef $spef
} else {
    log_cmd estimate_parasitics -global_routing
}

log_cmd report_power
report_power -format json > $::env(VECTORLESS_POWER_JSON)

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

log_cmd report_power
report_power -format json > $::env(VECTOR_DRIVEN_POWER_JSON)
