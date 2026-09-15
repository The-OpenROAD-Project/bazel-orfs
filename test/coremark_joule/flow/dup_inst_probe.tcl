# Where does a duplicate instance name in a written netlist come from?
#
# OpenROAD's write_verilog emitted two different AND2x2 clock cells under
# the name `_131758_` in one module of VeeR's global-route netlist. odb's
# own instance namespace is unique per block -- dbInst::create refuses a
# duplicate -- so the two cannot have that name in the database, and the
# collision must be created on the way out.
#
# This says so from the database rather than by inference: it prints, for
# each instance driving the two clock nets involved, the ODB name and the
# module it belongs to. If the ODB names differ and the emitted names do
# not, write_verilog's name mapping is not injective, and that is the
# bug to report.
#
# It also counts distinct instance names against instance count, so
# "odb cannot hold duplicates" is checked rather than assumed.
#
# Required env:
#   STAGE_STEM   ORFS stage stem, e.g. 5_1_grt
#   NETS         space-separated net names to look at
#   OUT          output path

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

set block [ord::get_db_block]
set fh [open $::env(OUT) w]

set insts [$block getInsts]
set names {}
foreach inst $insts {
    lappend names [$inst getName]
}
puts $fh "instances [llength $insts]"
puts $fh "distinct_names [llength [lsort -unique $names]]"

foreach net_name $::env(NETS) {
    set net [$block findNet $net_name]
    if { $net eq "NULL" || $net eq "" } {
        puts $fh "net $net_name MISSING"
        continue
    }
    puts $fh "net $net_name"
    foreach iterm [$net getITerms] {
        set inst [$iterm getInst]
        set module "(top)"
        set mi [$inst getModInst]
        if { $mi ne "NULL" && $mi ne "" } {
            set module [$mi getHierarchicalName]
        }
        puts $fh "  inst [$inst getName] master [[$inst getMaster] getName] pin [[$iterm getMTerm] getName] module $module"
    }
}
close $fh
