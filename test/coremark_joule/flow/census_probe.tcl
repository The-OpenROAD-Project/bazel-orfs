# Leaf instances and area under every module instance the ODB still has.
#
# Choosing which blocks to harden as macros starts with knowing what is
# big. The synthesis ODB keeps a module boundary for every kept module,
# so walking those boundaries and summing the leaf instances under each
# gives a census of the design at the granularity the flow can act on:
# a module that is not in the ODB cannot be hardened without first
# being kept.
#
# Two numbers per module instance: the leaf instances directly under it
# and the total including every module instance below, so a container
# whose own logic is small but whose children are large reads as large.
#
# Required env:
#   STAGE_STEM   ORFS stage stem, e.g. 1_synth
#   OUT          output path

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set dbu2 [expr { double($dbu) * $dbu }]

proc dict_get_default { d key default } {
    if { [dict exists $d $key] } {
        return [dict get $d $key]
    }
    return $default
}

# Direct leaf instances and their area per module, one pass over the
# instances, keyed by the module that owns each one.
set own_count [dict create]
set own_area [dict create]
foreach inst [$block getInsts] {
    set module [$inst getModule]
    if { $module eq "NULL" } {
        continue
    }
    set key [$module getName]
    set master [$inst getMaster]
    set area [expr { [$master getWidth] * [$master getHeight] / $dbu2 }]
    dict incr own_count $key
    dict set own_area $key [expr { [dict_get_default $own_area $key 0.0] + $area }]
}

# Totals by recursion over the module tree. A module is instantiated by
# its dbModInsts; the master of each is a dbModule with its own
# children.
proc census { module depth path fh } {
    global own_count own_area
    set key [$module getName]
    set count [dict_get_default $own_count $key 0]
    set area [dict_get_default $own_area $key 0.0]
    set total_count $count
    set total_area $area
    set rows {}
    foreach child [$module getChildren] {
        set sub [$child getMaster]
        set child_path "$path/[$child getName]"
        lassign [census $sub [expr { $depth + 1 }] $child_path $fh] c a
        set total_count [expr { $total_count + $c }]
        set total_area [expr { $total_area + $a }]
    }
    puts $fh [format "module %d %s %s own %d %.3f total %d %.3f" \
        $depth $path $key $count $area $total_count $total_area]
    return [list $total_count $total_area]
}

set top [$block getTopModule]
set fh [open $::env(OUT) w]
puts $fh "stage $::env(STAGE_STEM)"
puts $fh "top [$top getName]"
puts $fh "instances [llength [$block getInsts]]"
puts $fh "modinsts [llength [$block getModInsts]]"
puts $fh "columns: module depth path master own <count> <um2> total <count> <um2>"
census $top 0 [$top getName] $fh
close $fh
