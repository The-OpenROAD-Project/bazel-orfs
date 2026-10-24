# A flow stage read for comparing alternatives, at global route by
# default, where they are ranked (dogfooding rule 14). Writes whichever of
# these it is given, in the liberty's time unit:
#
# ENDPOINTS_OUT  every reg2reg endpoint's period, the clock period minus
#                its slack, "<endpoint>\t<period>" per line: the population
#                compare.py reads (ORFS #4583)
# REPORT_OUT     each path group's worst path, the reg2reg minimum period,
#                WNS and the hold buffers repair inserted:
#                  clock <period>
#                  <group> worst slack <slack>  <startpoint> -> <endpoint>
#                  reg2reg min period <period>
#                  wns <slack>
#                  worst hold slack <slack>
#                  hold buffers <count>
#                  die <w> x <h> um
#                  cell area <um2>, standard cells
#                  macro area <um2>, macro footprints
#
# READ_STAGE=place reads placement with its parasitics and an ideal
# clock, for a small test flow that stops there; READ_STAGE=cts reads the
# clock tree with placement parasitics; READ_STAGE=floorplan reads the
# netlist with ideal wires and clock, the logic alone.
source $::env(SCRIPTS_DIR)/load.tcl
set read_stage [expr { [info exists ::env(READ_STAGE)] ? $::env(READ_STAGE) : "grt" }]
if { $read_stage eq "grt" } {
  load_design 5_1_grt.odb 5_1_grt.sdc
  set_propagated_clock [all_clocks]
  estimate_parasitics -global_routing
} elseif { $read_stage eq "cts" } {
  load_design 4_cts.odb 4_cts.sdc
  set_propagated_clock [all_clocks]
  estimate_parasitics -placement
} elseif { $read_stage eq "place" } {
  load_design 3_place.odb 3_place.sdc
  estimate_parasitics -placement
} elseif { $read_stage eq "floorplan" } {
  load_design 2_floorplan.odb 2_floorplan.sdc
} else {
  error "READ_STAGE is grt, cts, place or floorplan, not $read_stage"
}

# The flow defines no path groups, and find_timing_paths -path_group then
# selects nothing in particular: it returns the worst path overall. Each
# group is selected by its ends instead.
set endpoint_band_groups [dict create \
  reg2reg [list -from [all_registers -clock_pins] -to [all_registers -data_pins]] \
  in2reg [list -from [all_inputs -no_clocks] -to [all_registers -data_pins]] \
  reg2out [list -from [all_registers -clock_pins] -to [all_outputs]] \
  in2out [list -from [all_inputs -no_clocks] -to [all_outputs]]]

set p [get_property [lindex [all_clocks] 0] period]

if { [info exists ::env(ENDPOINTS_OUT)] } {
  set ends [find_timing_paths {*}[dict get $endpoint_band_groups reg2reg] \
    -endpoint_path_count 1 -group_path_count [sta::endpoint_count] \
    -unique_paths_to_endpoint]
  set f [open $::env(ENDPOINTS_OUT) w]
  foreach t $ends {
    puts $f [format "%s\t%.6g" [get_full_name [get_property $t endpoint]] \
      [expr { $p - [get_property $t slack] }]]
  }
  close $f
}

if { [info exists ::env(REPORT_OUT)] } {
  set out [list [format "clock %.6g" $p]]
  dict for { g sel } $endpoint_band_groups {
    set ps [find_timing_paths {*}$sel -sort_by_slack -group_path_count 1]
    if { [llength $ps] } {
      set t [lindex $ps 0]
      lappend out [format "%-8s worst slack %.4g  %s -> %s" $g [get_property $t slack] \
        [get_full_name [get_property $t startpoint]] [get_full_name [get_property $t endpoint]]]
    } else {
      lappend out [format "%-8s no paths" $g]
    }
  }
  set ps [find_timing_paths {*}[dict get $endpoint_band_groups reg2reg] -sort_by_slack -group_path_count 1]
  # a block whose registers only feed its outputs, a register file's
  # slice, has no reg2reg path of its own: its period is its parent's
  if { [llength $ps] } {
    lappend out [format "reg2reg min period %.6g" [expr { $p - [get_property [lindex $ps 0] slack] }]]
  } else {
    lappend out "reg2reg min period none"
  }
  lappend out [format "wns %.4g" [sta::worst_slack -max]]
  set hold [find_timing_paths -path_delay min -sort_by_slack -group_path_count 1]
  if { [llength $hold] } {
    lappend out [format "worst hold slack %.4g" [get_property [lindex $hold 0] slack]]
  } else {
    lappend out "worst hold slack none"
  }
  # repair_timing -hold names the buffers it inserts hold<n>
  set n 0
  foreach inst [[ord::get_db_block] getInsts] {
    if { [string match "hold*" [$inst getName]] } { incr n }
  }
  lappend out "hold buffers $n"
  # the price side: the die, the standard cells on it (fill, taps and
  # decaps left out) and the macros' footprints
  set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
  set d [[ord::get_db_block] getDieArea]
  set cells 0.0
  set macros 0.0
  foreach inst [[ord::get_db_block] getInsts] {
    set m [$inst getMaster]
    set a [expr { [$m getWidth] / double($dbu) * [$m getHeight] / double($dbu) }]
    if { [$m isBlock] } { set macros [expr { $macros + $a }]; continue }
    if { [$m getType] eq "CORE_SPACER" || [string match -nocase *TAP* [$m getName]] || [string match -nocase *FILL* [$m getName]] || [string match -nocase *DECAP* [$m getName]] } { continue }
    set cells [expr { $cells + $a }]
  }
  lappend out [format "die %.3f x %.3f um" [expr { [$d dx] / double($dbu) }] [expr { [$d dy] / double($dbu) }]]
  lappend out [format "cell area %.1f um2" $cells]
  lappend out [format "macro area %.1f um2" $macros]
  set f [open $::env(REPORT_OUT) w]
  puts $f [join $out "\n"]
  close $f
}
