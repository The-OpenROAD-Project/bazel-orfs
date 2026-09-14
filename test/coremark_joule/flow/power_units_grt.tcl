# Per-functional-unit power at a pre-route stage.
#
# The whole-design number says how much energy a core spends; this says
# where. It is the reason the designs synthesize hierarchically with an
# explicit SYNTH_KEEP_MODULES and run OpenROAD with
# OPENROAD_HIERARCHICAL=1: module boundaries have to survive synthesis,
# placement, CTS and global route for there to be anything to attribute
# power to.
#
# The instance paths are discovered from the ODB rather than declared.
# A design states which modules are units (units.json); where those
# modules ended up instantiated is a fact about the netlist, and reading
# it back cannot drift the way a hand-written path can.
#
# Required env:
#   STAGE_STEM       ORFS stage stem, e.g. 5_1_grt
#   SAIF_STIMULI     path to the .saif
#   SAIF_SCOPE       hierarchy in the SAIF matching the design root
#   OUT_JSON         output path

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

log_cmd estimate_parasitics -global_routing
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

# Every module instance in the design, as module name -> instance paths.
# A module instantiated more than once contributes every instance.
set block [ord::get_db_block]

# Diagnostics: an empty breakdown and a design with no hierarchy look
# identical in the output, so say which it is. SERV reaches here with
# zero modinsts -- its kept modules are parameterized, so yosys names
# them `$paramod\serv_alu\W=...`, and that hierarchy does not survive
# into the ODB even though all thirteen modules are present in
# 1_2_yosys.v. picorv32's plainly named modules do survive.
set top [$block getTopModule]
puts "power_units: top module [$top getName]"
puts "power_units: block modinsts [llength [$block getModInsts]]"
puts "power_units: top children  [llength [$top getChildren]]"

set by_module [dict create]
foreach modinst [$block getModInsts] {
    set master [[$modinst getMaster] getName]
    set path [$modinst getHierarchicalName]
    dict lappend by_module $master $path
}

set out [open $::env(OUT_JSON) w]
puts $out "\{"
set first 1
dict for { module paths } $by_module {
    # report_power raises on a path it cannot resolve, and a module
    # boundary can survive in the ODB while its cells have been absorbed
    # elsewhere, so ask before reporting.
    set valid {}
    foreach p $paths {
        if { [get_cells -quiet $p] ne {} } {
            lappend valid $p
        }
    }
    if { [llength $valid] == 0 } {
        continue
    }
    set tmp [file join [file dirname $::env(OUT_JSON)] "power_unit_tmp.json"]
    report_power -format json -instances $valid > $tmp
    set fh [open $tmp r]
    set body [string trim [read $fh]]
    close $fh
    file delete -force $tmp
    if { !$first } {
        puts $out ","
    }
    set first 0
    puts -nonewline $out "  \"$module\": $body"
}
puts $out "\n\}"
close $out
