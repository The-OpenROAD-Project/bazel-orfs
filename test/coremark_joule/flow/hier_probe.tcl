# How much module hierarchy survives into a stage's ODB.
#
# An empty per-unit power breakdown and a design that never had any
# hierarchy look identical downstream, so this answers which it is, and
# at which stage it was lost.
source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

set block [ord::get_db_block]
set top [$block getTopModule]

set fh [open $::env(OUT) w]
puts $fh "stage $::env(STAGE_STEM)"
puts $fh "top [$top getName]"
puts $fh "modinsts [llength [$block getModInsts]]"
puts $fh "children [llength [$top getChildren]]"
foreach mi [$block getModInsts] {
    puts $fh "  modinst [$mi getName] of [[$mi getMaster] getName]"
}
close $fh
