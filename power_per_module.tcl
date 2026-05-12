# Per-module SAIF-driven report_power.
#
# Unlike power.tcl (which loads from verilog + link_design and flattens
# the hierarchy), this script loads from the ODB with `-hier`, so module
# instances stay visible to `get_cells` and we can break power down by
# instance group.
#
# Required env:
#   ODB_FILE                  hierarchical ODB to load
#   POWER_STAGE               ORFS stage stem for the SDC under RESULTS_DIR
#   RESULTS_DIR               ORFS results dir for $POWER_STAGE.sdc
#   SPEFS_AND_NETLISTS        mix of .v and .spef paths (only .spef
#                             matters here; .v is read from the ODB)
#   SAIF_SCOPE                OpenSTA hierarchy scope to map the SAIF
#                             onto (e.g. `TOP/<DESIGN_NAME>`)
#   SAIF_STIMULI              path to the .saif file
#   MODULE_INSTANCE_MAP       Tcl file containing a single dict literal
#                             whose values are lists of instance paths
#                             to roll up
#   OUT_JSON                  output path for the per-module power JSON
#
# Optional env:
#   SPEF_PATHS_TCL            same per-instance SPEF scoping hook as in
#                             power_base.tcl

source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
log_cmd read_db -hier $::env(ODB_FILE)
log_cmd read_sdc $::env(RESULTS_DIR)/$::env(POWER_STAGE).sdc

if { [info exists ::env(SPEF_PATHS_TCL)] && $::env(SPEF_PATHS_TCL) ne "" } {
    source $::env(SPEF_PATHS_TCL)
} else {
    foreach file $::env(SPEFS_AND_NETLISTS) {
        if { [string match *.spef $file] } {
            log_cmd read_spef $file
        }
    }
}

report_parasitic_annotation
report_units

set_case_analysis 0 reset

log_cmd report_checks

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

set fh [open $::env(MODULE_INSTANCE_MAP) r]
set dictData [read $fh]
close $fh
set d [dict create {*}$dictData]
set instance_list [dict values $d]
set instances [concat {*}$instance_list]

# Filter to instances that actually exist in this scope. report_power
# -instances raises STA-0127 on the first missing cell; the map can
# legitimately contain paths that aren't present at this stage (e.g.
# hardened-macro internals exposed at the model layer but not in this
# ODB), so silently skip them.
set valid_instances {}
foreach inst $instances {
    if { [get_cells -quiet $inst] ne {} } {
        lappend valid_instances $inst
    }
}
report_power -format json -instances $valid_instances > $::env(OUT_JSON)
