# SAIF-driven report_power at synthesis: no placement, no wires.
#
# The post-synthesis netlist has no placement, so there is nothing for
# estimate_parasitics to estimate from; report_power runs on cell
# capacitances alone. That is the configuration the near-miss study of
# §4.8 reports -- "power simulations have been performed using the
# post-synthesis netlists", PrimeTime, no clock tree -- and the point of
# this script is to take this study's number the same way so the two
# can be compared without a stage difference in between.
#
# Same two passes as power_grt.tcl, for the same reason: a SAIF that
# failed to bind is visible as two identical reports.
#
# Required env: as power_grt.tcl.

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

log_cmd report_power
report_power -format json > $::env(VECTORLESS_POWER_JSON)

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

log_cmd report_power
report_power -format json > $::env(VECTOR_DRIVEN_POWER_JSON)
