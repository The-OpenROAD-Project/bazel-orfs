# A part's KPI, read in the build: its reg2reg period (the SDC period minus the
# group's worst slack) and the worst path of each group, written to KPI_OUT.
# Every part, the parent and each block alone, is read at global route with the
# route's parasitics and its clock tree, as the README measures them
# (KPI_STAGE grt; place reads a place-stage checkpoint against an ideal clock).
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
# Every reg2reg endpoint's period (the SDC period minus its slack), in 10 ps
# bins from the first occupied one: the mass above a target, not only the
# worst path. Fine enough to rebin when drawing.
set bin 10
array set hist {}
set ends [find_timing_paths -path_group reg2reg -endpoint_path_count 1 \
  -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint]
foreach t $ends {
  set b [expr { int(floor(($p - [get_property $t slack]) / $bin)) }]
  if { [info exists hist($b)] } { incr hist($b) } else { set hist($b) 1 }
}
set bins [lsort -integer [array names hist]]
set counts {}
for { set b [lindex $bins 0] } { $b <= [lindex $bins end] } { incr b } {
  lappend counts [expr { [info exists hist($b)] ? $hist($b) : 0 }]
}
lappend out [format "reg2reg endpoints bin %d ps from %d ps: %s" $bin \
  [expr { [lindex $bins 0] * $bin }] [join $counts " "]]
lappend out [format "reg2reg min period %.0f ps" [expr { $p - $r2r }]]
set f [open $::env(KPI_OUT) w]
puts $f [join $out "\n"]
close $f
