# Whole-design SAIF-driven report_power.
#
# Runs two report_power passes:
#   1. vectorless — clock activity only (default OpenSTA assumptions)
#   2. vector-driven — clock + SAIF-annotated toggle activity for all nets
# and writes each as JSON to the env-supplied path.
#
# Required env:
#   POWER_BASE_TCL                  path to power_base.tcl (sources the
#                                   design, LEFs, libs, SPEF, SDC)
#   VECTORLESS_POWER_JSON           output path for the clock-only pass
#   VECTOR-DRIVEN_POWER_JSON        output path for the SAIF-annotated pass
#   SAIF_SCOPE                      OpenSTA hierarchy scope to map the
#                                   SAIF onto (e.g. `TOP/<DESIGN_NAME>`).
#                                   The SAIF-emitting simulator usually
#                                   wraps the DUT inside one or more
#                                   testbench modules; SAIF_SCOPE tells
#                                   read_saif which sub-hierarchy in
#                                   the SAIF file corresponds to the
#                                   linked design root.
#   SAIF_STIMULI                    path to the .saif file

source $::env(POWER_BASE_TCL)

log_cmd report_power
report_power -format json > $::env(VECTORLESS_POWER_JSON)

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

log_cmd report_power
report_power -format json > $::env(VECTOR-DRIVEN_POWER_JSON)
