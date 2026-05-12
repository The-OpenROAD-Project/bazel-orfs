# Shared design-loading preamble for the SAIF -> OpenSTA power flow.
#
# Loads the gate-level netlist, technology+stdcell LEFs, Liberty files,
# SDC, and parasitics, then links the design ready for `report_power`.
#
# Sourced by power.tcl (whole-design) and power_per_module.tcl
# (per-instance roll-up).
#
# Required env:
#   DESIGN_NAME            top-level Verilog module to link
#   POWER_STAGE            ORFS stage stem used to find the SDC under RESULTS_DIR
#   RESULTS_DIR            ORFS results dir for $POWER_STAGE.sdc
#   LIB_FILES              Liberty files to read
#   SPEFS_AND_NETLISTS     mix of .v (gate-level netlist) and .spef
#                          (parasitics) file paths
#   TECH_LEF, SC_LEF       optional; if TECH_LEF is set, reads the tech LEF
#                          plus each SC_LEF and any ADDITIONAL_LEFS.
#
# Optional env:
#   SPEF_PATHS_TCL         path to a Tcl snippet that reads SPEF files with
#                          per-instance `-path` scoping. When set, the
#                          default `read_spef <file>` loop is replaced by
#                          sourcing this file. Use when a design has
#                          multiple SPEFs under different instance scopes
#                          (e.g. hardened macro plus parent's own SPEF).

source $::env(SCRIPTS_DIR)/util.tcl

if { [info exists ::env(TECH_LEF)] } {
    read_lef $::env(TECH_LEF)
    foreach lef $::env(SC_LEF) {
        read_lef $lef
    }
    if { [info exists ::env(ADDITIONAL_LEFS)] } {
        foreach lef $::env(ADDITIONAL_LEFS) {
            read_lef $lef
        }
    }
}

foreach libFile $::env(LIB_FILES) {
    log_cmd read_liberty $libFile
}

foreach file $::env(SPEFS_AND_NETLISTS) {
    if { [string match *.v $file] } {
        log_cmd read_verilog $file
    }
}

log_cmd link_design $::env(DESIGN_NAME)
log_cmd read_sdc $::env(RESULTS_DIR)/$::env(POWER_STAGE).sdc

if { [info exists ::env(SPEF_PATHS_TCL)] && $::env(SPEF_PATHS_TCL) ne "" } {
    # Caller supplies per-instance SPEF scoping in a separate Tcl file.
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
