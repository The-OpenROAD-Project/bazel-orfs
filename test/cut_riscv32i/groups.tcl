# What decides an SDC for the ORFS pull request, at global route: each
# path group's worst slack and endpoint (WNS must be a reg2reg path), the
# reg2reg minimum period, and the hold buffers repair inserted (no hold
# infestation), to REPORT_OUT.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_1_grt.odb 5_1_grt.sdc
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing
set p [get_property [lindex [all_clocks] 0] period]
set out [list [format "clock %.6g" $p]]
# each group selected explicitly: the flow defines no path groups, and
# -path_group names one only where an SDC made it
set groups [dict create \
  reg2reg [list -from [all_registers -clock_pins] -to [all_registers -data_pins]] \
  in2reg [list -from [all_inputs -no_clocks] -to [all_registers -data_pins]] \
  reg2out [list -from [all_registers -clock_pins] -to [all_outputs]] \
  in2out [list -from [all_inputs -no_clocks] -to [all_outputs]]]
dict for { g sel } $groups {
  set ps [find_timing_paths {*}$sel -sort_by_slack -group_path_count 1]
  if { [llength $ps] } {
    set t [lindex $ps 0]
    lappend out [format "%-8s worst slack %.4g  %s -> %s" $g [get_property $t slack] \
      [get_full_name [get_property $t startpoint]] [get_full_name [get_property $t endpoint]]]
  } else {
    lappend out [format "%-8s no paths" $g]
  }
}
set ps [find_timing_paths {*}[dict get $groups reg2reg] -sort_by_slack -group_path_count 1]
lappend out [format "reg2reg min period %.6g" [expr { $p - [get_property [lindex $ps 0] slack] }]]
set ws [sta::worst_slack -max]
lappend out [format "wns %.4g" $ws]
set hold [find_timing_paths -path_delay min -sort_by_slack -group_path_count 1]
lappend out [format "worst hold slack %.4g" [get_property [lindex $hold 0] slack]]
# hold buffers: cells repair_timing -hold names hold*
set n 0
foreach inst [[ord::get_db_block] getInsts] {
  if { [string match "hold*" [$inst getName]] } { incr n }
}
lappend out "hold buffers $n"
set f [open $::env(REPORT_OUT) w]
puts $f [join $out "\n"]
close $f
