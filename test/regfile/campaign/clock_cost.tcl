# The clock tree's cost at global route: hold, the clock tree's cells and
# area, the clock gates, and power split by group. One line.
if {[catch {estimate_parasitics -global_routing}]} {estimate_parasitics -placement}
set b [ord::get_db_block]; set u [$b getDbUnitsPerMicron]
set bufs 0; set barea 0; set icg 0
foreach i [$b getInsts] {
  set m [$i getMaster]; set n [$m getName]
  if {[string match ICG* $n]} {incr icg; continue}
  if {![string match {*BUF*} $n] && ![string match {*INV*} $n]} continue
  set clk 0
  foreach it [$i getITerms] {
    set net [$it getNet]
    if {$net ne "NULL" && [$it isOutputSignal] && [$net getSigType] eq "CLOCK"} {set clk 1}
  }
  if {$clk} {incr bufs; set barea [expr {$barea + double([$m getWidth])*[$m getHeight]/$u/$u}]}
}
set hold [sta::worst_slack -min]
set hn 0
foreach t [find_timing_paths -path_delay min -group_path_count 100000 -endpoint_path_count 1 -slack_max 0] {incr hn}
sta::with_output_to_variable pr { report_power }
regexp -line {^Total\s+\S+\s+\S+\s+\S+\s+(\S+)} $pr -> ptot
regexp -line {^Clock\s+\S+\s+\S+\s+\S+\s+(\S+)} $pr -> pclk
format "hold WNS %.1f ps, %d hold-failing endpoints; clock tree %d buffers/inverters %.1f um2; %d clock gates; power total %s W, clock %s W" \
  $hold $hn $bufs $barea $icg $ptot $pclk
