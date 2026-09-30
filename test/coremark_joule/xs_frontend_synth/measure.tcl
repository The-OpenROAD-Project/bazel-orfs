# xs_measure TAG OUT RPT: one line into OUT, the reg2reg minimum period
# (the SDC period minus the group's worst slack), the reg2reg endpoints
# whose worst path needs more than 1,000 and 950 ps, the BUF cells and
# the other groups' worst slack; the worst reg2reg path into RPT.
proc xs_over {ps} {
  set clk_ps [expr {[get_property [sta::find_clock clk] period]}]
  return [llength [find_timing_paths -path_group reg2reg -path_delay max \
    -group_path_count 1000000 -endpoint_path_count 1 \
    -slack_max [expr {$clk_ps - $ps}] -unique_paths_to_endpoint]]
}
proc xs_measure {tag out rpt} {
  set clk_ps [get_property [sta::find_clock clk] period]
  set p [find_timing_paths -path_group reg2reg -path_delay max -group_path_count 1]
  set s [sta::format_time [[lindex $p 0] slack] 1]
  set nb 0
  foreach i [[ord::get_db_block] getInsts] {
    if {[string match BUF* [[$i getMaster] getName]]} { incr nb }
  }
  set g {}
  foreach grp {in2reg reg2out in2out} {
    set q [find_timing_paths -path_group $grp -path_delay max -group_path_count 1]
    if {[llength $q]} { lappend g "$grp [sta::format_time [[lindex $q 0] slack] 1]" }
  }
  set f [open $out a]
  puts $f "$tag: reg2reg WNS $s ps (period [format %.1f [expr {$clk_ps - $s}]] ps),\
over 1000 ps [xs_over 1000], over 950 ps [xs_over 950], BUF cells $nb,\
insts [llength [[ord::get_db_block] getInsts]]; [join $g {, }]"
  close $f
  report_checks -path_group reg2reg -path_delay max -fields {slew cap fanout} -digits 1 > $rpt
}
