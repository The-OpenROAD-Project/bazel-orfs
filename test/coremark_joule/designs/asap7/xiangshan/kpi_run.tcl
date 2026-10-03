# A part's KPI, read in the build: its reg2reg period (the SDC period minus the
# group's worst slack) and the worst path of each group, written to KPI_OUT.
# The parent is read at global route with the route's parasitics and its clock
# tree; each block alone at its place stage against an ideal clock, as the
# README measures them (KPI_STAGE grt or place).
source $::env(SCRIPTS_DIR)/load.tcl
if { $::env(KPI_STAGE) eq "grt" } {
  load_design 5_1_grt.odb 5_1_grt.sdc
  set_propagated_clock [all_clocks]
  estimate_parasitics -global_routing
} else {
  load_design 3_place.odb 3_place.sdc
  estimate_parasitics -placement
}
set p [get_property [get_clocks] period]
set out {}
foreach g {reg2reg in2reg reg2out in2out} {
  set ps [find_timing_paths -path_group $g -sort_by_slack -group_path_count 1]
  if { [llength $ps] } {
    set t [lindex $ps 0]
    lappend out [format "%-8s %8.0f ps  %s -> %s" $g [get_property $t slack] \
      [get_full_name [get_property $t startpoint]] [get_full_name [get_property $t endpoint]]]
    if { $g eq "reg2reg" } { set r2r [get_property $t slack] }
  }
}
lappend out [format "reg2reg min period %.0f ps" [expr { $p - $r2r }]]
set f [open $::env(KPI_OUT) w]
puts $f [join $out "\n"]
close $f
