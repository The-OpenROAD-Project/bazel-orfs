# One row of the wire campaign (docs/plans/xstile-wire-campaign.md) from a
# place checkpoint: the reg2reg period with the flow's placement
# parasitics, the same period with every wire priced at nothing (the
# floor), the half-perimeter wirelength, and how much wire the worst path
# crosses. The clock is ideal: nothing is propagated before CTS.
#
# The load and the parasitics are the flow's own (load.tcl, then the
# estimate_parasitics -placement open.tcl runs at place): a hand-rolled
# read_db prices wires differently and was 1.8x off on Frontend.
#
# Required env:
#   OUTPUT_JSON  where the row goes
# Optional env:
#   STAGE_STEM   checkpoint stem, default 3_place
source $::env(SCRIPTS_DIR)/load.tcl
set stem 3_place
if { [info exists ::env(STAGE_STEM)] } {
  set stem $::env(STAGE_STEM)
}
load_design $stem.odb $stem.sdc
estimate_parasitics -placement

set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set clk [lindex [all_clocks] 0]
set period [get_property $clk period]

# The group is the platform's (constraints.sdc's group_path), asked for
# by name: the overall worst slack belongs to whatever group is worst,
# and only reg2reg is a period (.claude/skills/macro-constraints).
proc reg2reg_worst {} {
  set paths [find_timing_paths -path_group reg2reg -sort_by_slack \
    -group_path_count 1]
  if { [llength $paths] == 0 } {
    error "wire_probe: the reg2reg group has no paths; is the platform's\
      constraints.sdc sourced?"
  }
  return [lindex $paths 0]
}

# Wire on a path: for each net it crosses, the Manhattan distance from
# the driver's pin to the load's, at their placed shapes (a macro pin
# where it is on the macro, not at the macro's centre).
proc path_wire_um { path dbu } {
  set total 0
  set prev ""
  foreach point [get_property $path points] {
    set pin [get_property $point pin]
    set iterm [sta::sta_to_db_pin $pin]
    if { $iterm ne "NULL" && $iterm ne "" } {
      set box [$iterm getBBox]
    } else {
      set bterm [[ord::get_db_block] findBTerm [get_full_name $pin]]
      if { $bterm eq "NULL" || $bterm eq "" } {
        continue
      }
      set box [$bterm getBBox]
    }
    set xy [list [expr { ([$box xMin] + [$box xMax]) / 2 }] \
      [expr { ([$box yMin] + [$box yMax]) / 2 }]]
    # A hop from an output to an input is a wire; from an input to the
    # same cell's output it is the cell.
    if { $prev ne "" && [get_property $pin direction] eq "input" } {
      set total [expr { $total + abs([lindex $xy 0] - [lindex $prev 0]) \
        + abs([lindex $xy 1] - [lindex $prev 1]) }]
    }
    set prev $xy
  }
  return [expr { double($total) / $dbu }]
}

set path [reg2reg_worst]
set slack [get_property $path slack]
set from [get_full_name [get_property $path startpoint]]
set to [get_full_name [get_property $path endpoint]]
set wire_um [path_wire_um $path $dbu]

# Half-perimeter wirelength over the signal nets, from the placement.
set hpwl 0
foreach net [$block getNets] {
  if { [$net getSigType] ne "SIGNAL" } {
    continue
  }
  set box [$net getTermBBox]
  set hpwl [expr { $hpwl + ([$box xMax] - [$box xMin]) \
    + ([$box yMax] - [$box yMin]) }]
}
set hpwl_m [expr { double($hpwl) / $dbu / 1e6 }]

# The floor: every routing, cut and wire RC at 1e-6. An RC of 0 is taken
# as unset by set_layer_rc and set_wire_rc, and the period does not move
# (ideas/xiangshan-timing.md, entry 37).
foreach layer [[ord::get_db_tech] getLayers] {
  set type [$layer getType]
  if { $type eq "ROUTING" } {
    set_layer_rc -layer [$layer getName] -resistance 1e-6 -capacitance 1e-6
  } elseif { $type eq "CUT" } {
    set_layer_rc -via [$layer getName] -resistance 1e-6
  }
}
set_wire_rc -signal -resistance 1e-6 -capacitance 1e-6
set_wire_rc -clock -resistance 1e-6 -capacitance 1e-6
estimate_parasitics -placement
set floor_path [reg2reg_worst]
set floor_slack [get_property $floor_path slack]

# From the stage's own logs (src_logs): what each place step cost, and
# the congestion global placement settled on. Routability-driven
# placement reverts to the least congested snapshot it saw (GPL-0089),
# so the smallest top-2% figure is the one it kept.
proc read_log { name } {
  set path [file join $::env(LOG_DIR) $name]
  if { ![file exists $path] } {
    return ""
  }
  set fp [open $path r]
  set text [read $fp]
  close $fp
  return $text
}
set steps {}
foreach log [lsort [glob -nocomplain -directory $::env(LOG_DIR) 3_*.log]] {
  set text [read_log [file tail $log]]
  if { [regexp {Elapsed time: (\S+)\[h:\]min:sec.*Peak memory: (\d+)KB} \
      $text - elapsed peak_kb] } {
    lappend steps "    \"[file rootname [file tail $log]]\":\
      {\"elapsed\": \"$elapsed\", \"peak_gib\":\
      [format %.2f [expr { $peak_kb / 1048576.0 }]]}"
  }
}
# Global placement runs in 3_3, or in 3_1 alone when both driven modes
# are off (patch 0077); the last log that placed is the one to read.
set gp [read_log 3_3_place_gp.log]
if { ![regexp {GPL-0023} $gp] } {
  set gp [read_log 3_1_place_gp_skip_io.log]
}
set gp_instances null
regexp {GPL-0006\] Number of instances:\s+(\d+)} $gp - gp_instances
set congestion null
foreach {- c} [regexp -all -inline {Average top 2.0% routing congestion: (\S+)} $gp] {
  if { $congestion eq "null" || $c < $congestion } {
    set congestion $c
  }
}
set density null
regexp {GPL-0023\] Placement target density:\s+(\S+)} $gp - density

set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"stage\": \"$stem\","
puts $out "  \"clock_period_ps\": [format %.1f $period],"
puts $out "  \"period_ps\": [format %.1f [expr { $period - $slack }]],"
puts $out "  \"floor_ps\": [format %.1f [expr { $period - $floor_slack }]],"
puts $out "  \"worst_from\": \"$from\","
puts $out "  \"worst_to\": \"$to\","
puts $out "  \"worst_wire_um\": [format %.1f $wire_um],"
puts $out "  \"hpwl_m\": [format %.4f $hpwl_m],"
puts $out "  \"target_density\": $density,"
puts $out "  \"gp_instances\": $gp_instances,"
puts $out "  \"rudy_top2_congestion\": $congestion,"
puts $out "  \"steps\": {"
puts $out [join $steps ",\n"]
puts $out "  }"
puts $out "}"
close $out
