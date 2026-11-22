# The flat reference for the power shards: the parent's global-route ODB
# with each block dissolved into the cells, nets and route guides of the
# block's own global route (dissolve_macro, OpenROAD patch 0171), its
# clock tree kept, then report_power as power_grt.tcl runs it, at the
# parent's SAIF scope. The same cells where the shards have them and the
# same global routes, so the shards' sum and this differ only by how the
# shards see each other across a boundary.
#
# The dissolve has to come before the first command that reads the
# global routes: estimate_parasitics -global_routing then loads every
# net's routes from its guides, the dissolved nets' included.
#
# Required env:
#   STAGE_STEM               ORFS stage stem, 5_1_grt
#   DISSOLVE                 pairs: block instance, the block's 5_1_grt.odb
#   SAIF_STIMULI             path to the .saif
#   SAIF_SCOPE               the parent's scope in the SAIF
#   VECTORLESS_POWER_JSON    output
#   VECTOR_DRIVEN_POWER_JSON output
#   ANNOTATION_TXT           output: report_activity_annotation
#   POWER_PARASITICS         optional: global_routing (default) or placement

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb

set block [ord::get_db_block]
foreach {inst odb_file} $::env(DISSOLVE) {
    if { [$block findInst $inst] eq "NULL" } {
        error "power_flat: no instance $inst"
    }
    dissolve_macro -inst $inst -db $odb_file
    puts "power_flat: $inst dissolved from $odb_file"
}
# A flat block's cells carry its hierarchy as `/` in their names, which
# a SAIF cannot: the simulated netlist spells it __SL__
# (scripts/slash_names.py), and so does this, under each block's module
# instance, as the block's shard does in its own ODB.
set renamed 0
foreach {inst odb_file} $::env(DISSOLVE) {
    foreach cell [$block getInsts] {
        set n [$cell getName]
        if { [string first "$inst/" $n] == 0 } {
            set rest [string range $n [string length "$inst/"] end]
            if { [string first / $rest] >= 0 } {
                $cell rename "$inst/[string map {/ __SL__} $rest]"
                incr renamed
            }
        }
    }
}
puts "power_flat: $renamed dissolved cell names spelled with __SL__"
set macros 0
foreach inst [$block getInsts] {
    if { [$inst isBlock] } { incr macros }
}
if { $macros != 0 } {
    error "power_flat: $macros macros left after the dissolve; the reference must be flat"
}
puts "power_flat: [llength [$block getInsts]] instances, [llength [$block getNets]] nets"

set parasitics global_routing
if { [info exists ::env(POWER_PARASITICS)] } {
    set parasitics $::env(POWER_PARASITICS)
}
log_cmd estimate_parasitics -$parasitics

set digits 6
report_power -digits $digits
report_power -format json -digits $digits > $::env(VECTORLESS_POWER_JSON)

log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)
report_activity_annotation > $::env(ANNOTATION_TXT)

report_power -digits $digits
report_power -format json -digits $digits > $::env(VECTOR_DRIVEN_POWER_JSON)
