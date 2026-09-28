# The flow's pathologies on a loaded stage: one JSON record per call.
#   pathology_record OUT_JSON ?KEPT_EXPECTED?
# Design-rule violators and the worst slew, nets longer than LONG_NET_UM,
# the reg2reg period and the share of its worst path spent in one stage,
# the kept module definitions against a stated list, check_placement.
# Timing uses whatever parasitics the caller set up (estimate_parasitics).

namespace eval pathology {
  variable long_net_um 200.0
}

proc pathology::json_str {s} {
  return "\"[string map {\\ \\\\ \" \\\" \n \\n} $s]\""
}

proc pathology::period {rpt} {
  report_checks -path_group reg2reg -path_delay max -fields {slew cap fanout} -digits 1 > $rpt
  set f [open $rpt r]; set text [read $f]; close $f
  set slack ""
  regexp {(-?[0-9.]+)\s+slack} $text -> slack
  set arrival ""
  regexp {([0-9.]+)\s+data arrival time} $text -> arrival
  # The largest single stage (a cell and the net into it) on the path.
  set worst 0.0
  set worst_stage ""
  foreach line [split $text "\n"] {
    if {[regexp {^\s*\d+\s+[0-9.]+\s+[0-9.]+\s+([0-9.]+)\s+[0-9.]+\s+[v^]\s+(\S+)} $line -> d pin]} {
      if {$d > $worst} { set worst $d; set worst_stage $pin }
    }
  }
  set sp ""; set ep ""
  regexp {Startpoint: (\S+)} $text -> sp
  regexp {Endpoint: (\S+)} $text -> ep
  return [list $slack $arrival $worst $worst_stage $sp $ep]
}

# A net that reaches a clock pin: before CTS the clock is one long net by
# design, and not a pathology of placement.
proc pathology::is_clock_net {net} {
  foreach it [$net getITerms] {
    if {[$it getSigType] eq "CLOCK"} { return 1 }
  }
  return 0
}

proc pathology::long_nets {} {
  variable long_net_um
  set block [ord::get_db_block]
  set lim [expr {$long_net_um * [$block getDbUnitsPerMicron]}]
  set n 0
  set worst 0
  set worst_name ""
  foreach net [$block getNets] {
    if {[$net getSigType] ne "SIGNAL"} { continue }
    set bb [$net getTermBBox]
    set hp [expr {[$bb dx] + [$bb dy]}]
    if {$hp > $lim && ![pathology::is_clock_net $net]} {
      incr n
      if {$hp > $worst} { set worst $hp; set worst_name [$net getName] }
    }
  }
  return [list $n [expr {$worst / double([$block getDbUnitsPerMicron])}] $worst_name]
}

proc pathology::fanout_violators {rpt} {
  report_check_types -max_fanout -violators > $rpt
  set f [open $rpt r]; set text [read $f]; close $f
  return [regexp -all {VIOLATED} $text]
}

proc pathology::kept {} {
  set names {}
  foreach m [[ord::get_db_block] getModules] {
    lappend names [regsub {\$.*} [$m getName] {}]
  }
  return [lsort -unique $names]
}

proc pathology_record {out {kept_expected ""}} {
  set t0 [clock milliseconds]
  set design [[ord::get_db_block] getName]
  set slew [sta::max_slew_violation_count]
  set cap [sta::max_capacitance_violation_count]
  # sta::max_fanout_violation_count stops OpenROAD with signal 11 on
  # MainBtb; the report's violators are counted instead.
  set fanout [pathology::fanout_violators [file rootname $out].fanout.rpt]
  lassign [pathology::period [file rootname $out].path.rpt] slack arrival stage_ps stage_pin sp ep
  set clk [lindex [all_clocks] 0]
  set period [get_property $clk period]
  set period_ps [expr {$slack eq "" ? "null" : $period - $slack}]
  set share [expr {$arrival eq "" || $arrival == 0 ? "null" : $stage_ps / $arrival}]
  lassign [pathology::long_nets] long_n long_worst long_worst_name
  set kept [pathology::kept]
  set placement_ok [expr {[catch {check_placement} msg] ? "false" : "true"}]
  set f [open $out w]
  puts $f "\{"
  puts $f "  \"design\": [pathology::json_str $design],"
  puts $f "  \"slew_viol\": $slew,"
  puts $f "  \"cap_viol\": $cap,"
  puts $f "  \"fanout_viol\": $fanout,"
  puts $f "  \"long_nets\": $long_n,"
  puts $f "  \"long_net_worst_um\": $long_worst,"
  puts $f "  \"long_net_worst\": [pathology::json_str $long_worst_name],"
  puts $f "  \"period_ps\": $period_ps,"
  puts $f "  \"worst_startpoint\": [pathology::json_str $sp],"
  puts $f "  \"worst_endpoint\": [pathology::json_str $ep],"
  puts $f "  \"worst_stage_ps\": $stage_ps,"
  puts $f "  \"worst_stage\": [pathology::json_str $stage_pin],"
  puts $f "  \"worst_stage_share\": $share,"
  puts $f "  \"kept\": \[[join [lmap k $kept {pathology::json_str $k}] {, }]\],"
  puts $f "  \"kept_expected\": \[[join [lmap k [lsort -unique $kept_expected] {pathology::json_str $k}] {, }]\],"
  puts $f "  \"placement_ok\": $placement_ok,"
  puts $f "  \"probe_s\": [expr {([clock milliseconds] - $t0) / 1000.0}]"
  puts $f "\}"
  close $f
  return $out
}
