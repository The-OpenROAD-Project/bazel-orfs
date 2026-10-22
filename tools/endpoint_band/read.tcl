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
#
# READ_STAGE=place reads placement with its parasitics and an ideal
# clock, for a small test flow that stops there.
source $::env(SCRIPTS_DIR)/load.tcl
set read_stage [expr { [info exists ::env(READ_STAGE)] ? $::env(READ_STAGE) : "grt" }]
if { $read_stage eq "grt" } {
  load_design 5_1_grt.odb 5_1_grt.sdc
  set_propagated_clock [all_clocks]
  estimate_parasitics -global_routing
} elseif { $read_stage eq "place" } {
  load_design 3_place.odb 3_place.sdc
  estimate_parasitics -placement
} else {
  error "READ_STAGE is grt or place, not $read_stage"
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
  lappend out [format "reg2reg min period %.6g" [expr { $p - [get_property [lindex $ps 0] slack] }]]
  lappend out [format "wns %.4g" [sta::worst_slack -max]]
  set hold [find_timing_paths -path_delay min -sort_by_slack -group_path_count 1]
  lappend out [format "worst hold slack %.4g" [get_property [lindex $hold 0] slack]]
  # repair_timing -hold names the buffers it inserts hold<n>
  set n 0
  foreach inst [[ord::get_db_block] getInsts] {
    if { [string match "hold*" [$inst getName]] } { incr n }
  }
  lappend out "hold buffers $n"
  set f [open $::env(REPORT_OUT) w]
  puts $f [join $out "\n"]
  close $f
}
