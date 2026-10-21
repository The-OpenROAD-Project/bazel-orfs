# One arm's numbers at grt, reg2reg only: period, violating endpoints and
# their total, the one-flop-loop floor with its stages and buffers, buffer
# count and area, as one line to MEASURE_OUT. Run with `make run` in an arm's
# dirty lane (arm.sh).
source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_1_grt.odb 5_1_grt.sdc
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing
set p [get_property [lindex [all_clocks] 0] period]
set worst ""
set viol 0
set tns 0.0
foreach pe [find_timing_paths -from [all_registers -clock_pins] -to [all_registers -data_pins] \
              -endpoint_path_count 1 -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint] {
  set s [get_property $pe slack]
  if { $worst eq "" || $s < $worst } { set worst $s }
  if { $s < 0 } {
    incr viol
    set tns [expr { $tns + $s }]
  }
}
# report_floor_cycles.tcl reports when sourced; keep its line
set ::floor_line ""
rename puts measure_puts
proc puts { args } {
  set ::floor_line [lindex $args end]
  measure_puts {*}$args
}
source [file join [file dirname [info script]] .. report_floor_cycles.tcl]
rename puts {}
rename measure_puts puts
set bufnames [dict create]
foreach lc [get_lib_cells -quiet */*] {
  if { [get_property $lc is_buffer] } { dict set bufnames [get_name $lc] 1 }
}
set bufs 0
foreach inst [get_cells *] {
  if { [dict exists $bufnames [get_property $inst ref_name]] } { incr bufs }
}
set f [open $::env(MEASURE_OUT) w]
puts $f [format "period %.1f r2r_violating %d r2r_tns %.1f buffers %d area %.1f | %s" \
  [expr { $p - $worst }] $viol $tns $bufs [expr { [rsz::design_area] * 1e12 }] $::floor_line]
close $f
