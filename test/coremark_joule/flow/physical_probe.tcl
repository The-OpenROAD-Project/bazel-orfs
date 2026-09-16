# The physical numbers a literature comparison needs, from one stage's ODB.
#
# §4.9 of the study compares each core against what its authors and
# others have published: gate equivalents, minimum clock period,
# CoreMark/MHz and CoreMark/Joule. The published side of that table is
# pinned in pin_results.py; this is the measured side, taken from the
# same ODB the power was, so the two columns describe the same netlist.
#
# Gate equivalents follow the convention every paper in that table uses:
# standard-cell area divided by the area of the library's two-input NAND
# at its smallest drive. Which NAND that is differs by kit and the
# papers rarely say, so the cell is an input (GE_CELL) and its area is
# written next to the count, so a reader can redo the division against
# whatever NAND their own source meant.
#
# Macros are reported separately and are *not* in the gate count: a
# gate-equivalent figure for an SRAM is not a thing the literature
# quotes, and the papers whose cores carry caches state their kGE for the
# core with the caches taken out (or, more often, do not say).
#
# Required env:
#   STAGE_STEM   ORFS stage stem, e.g. 5_1_grt
#   GE_CELL      the NAND2 whose area is one gate equivalent
#   OUT          output path

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set dbu2 [expr { double($dbu) * $dbu }]

# Areas by master first: ten million instances is too many to ask STA
# about one at a time, and a master's class does not change per instance.
set by_master [dict create]
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    dict incr by_master [$master getName]
}

set stdcell_area 0.0
set stdcell_count 0
set macro_area 0.0
set macro_count 0
set fill_count 0
set physical_count 0
set macro_lines {}
foreach {name count} $by_master {
    set master [[ord::get_db] findMaster $name]
    set area [expr { [$master getWidth] * [$master getHeight] / $dbu2 }]
    if { [$master isBlock] } {
        set macro_area [expr { $macro_area + $area * $count }]
        incr macro_count $count
        lappend macro_lines "macro $name $count [format %.4f $area]"
        continue
    }
    if { [$master isFiller] } {
        incr fill_count $count
        continue
    }
    # Tap cells, tie cells, endcaps, and anything else with no timing
    # arc are physical rather than logical: they belong to the
    # implementation of the row, not to the architecture. The
    # dbMasterType carries the LEF CLASS; CORE SPACER/ANTENNACELL/WELLTAP
    # and ENDCAP are the ones asap7 emits.
    set type [$master getType]
    if { [string match "CORE_SPACER" $type] || [string match "CORE_WELLTAP" $type] \
        || [string match "CORE_ANTENNACELL" $type] || [string match "ENDCAP*" $type] } {
        incr physical_count $count
        continue
    }
    set stdcell_area [expr { $stdcell_area + $area * $count }]
    incr stdcell_count $count
}

set ge_cell $::env(GE_CELL)
set ge_master [[ord::get_db] findMaster $ge_cell]
if { $ge_master eq "NULL" } {
    error "physical_probe: GE_CELL $ge_cell is not a master in this design's LEFs"
}
set nand2_area [expr { [$ge_master getWidth] * [$ge_master getHeight] / $dbu2 }]

# Flops from STA rather than from a naming convention: all_registers is
# what the liberty says is sequential, which asap7's DFF*/SDF*/DHL*
# names would also give, but only by luck.
set flops [llength [all_registers -cells]]

# Clock period and the reg2reg slack, the same way period_probe.tcl
# takes it (§3.8: the overall WNS is limited by this study's IO budget,
# a property of the SDC and not of the core). Parasitics as the stage
# allows: routing estimates once there are route guides, placement
# estimates before that.
if { [string match "5_*" $::env(STAGE_STEM)] || [string match "6_*" $::env(STAGE_STEM)] } {
    log_cmd estimate_parasitics -global_routing
} else {
    log_cmd estimate_parasitics -placement
}
set clk [lindex [all_clocks] 0]
set period [get_property $clk period]
set reg2reg_ps "none"
set paths [find_timing_paths -path_group reg2reg -sort_by_slack -group_path_count 1]
if { [llength $paths] > 0 } {
    set reg2reg_ps [get_property [lindex $paths 0] slack]
}

set die [$block getDieArea]
set core [$block getCoreArea]
set die_um2 [expr { [$die dx] * [$die dy] / $dbu2 }]
set core_um2 [expr { [$core dx] * [$core dy] / $dbu2 }]

set fh [open $::env(OUT) w]
puts $fh "stage $::env(STAGE_STEM)"
puts $fh "design [$block getName]"
puts $fh "die_um2 [format %.1f $die_um2]"
puts $fh "core_um2 [format %.1f $core_um2]"
puts $fh "stdcell_count $stdcell_count"
puts $fh "stdcell_um2 [format %.3f $stdcell_area]"
puts $fh "physical_count $physical_count"
puts $fh "fill_count $fill_count"
puts $fh "flops $flops"
puts $fh "macro_count $macro_count"
puts $fh "macro_um2 [format %.3f $macro_area]"
puts $fh "ge_cell $ge_cell"
puts $fh "nand2_um2 [format %.6f $nand2_area]"
puts $fh "gate_equivalents [format %.0f [expr { $stdcell_area / $nand2_area }]]"
puts $fh "kge [format %.1f [expr { $stdcell_area / $nand2_area / 1000.0 }]]"
puts $fh "clock [get_name $clk]"
puts $fh "period_ps $period"
puts $fh "wns_reg2reg_ps $reg2reg_ps"
if { $reg2reg_ps ne "none" } {
    puts $fh "achieved_period_ps [expr { $period - $reg2reg_ps }]"
}
foreach line $macro_lines {
    puts $fh $line
}
close $fh
