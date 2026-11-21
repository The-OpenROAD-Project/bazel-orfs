# The routed wire's delay per micron, for the planner's wire model
# (pdk.json's ps_per_um): on a global-routed stage, every signal net
# whose driver and farthest load are at least PROBE_MIN_UM apart, the
# arrival at that load less the arrival at the driver's output (the
# wire's delay with the parasitics global route estimates, no cell),
# over their Manhattan distance. One line per net to PROBE_OUT:
#
#   <distance um> <wire ps> <ps per um> <net>
#
# A net the resizer repeated is several nets, each a span between
# repeaters: the distribution is the repeated wire's, which is what the
# planner charges.
#
#   PROBE_OUT     the dump
#   PROBE_MIN_UM  the shortest span counted (20)
#   PROBE_STAGE   the stage's ODB (5_1_grt.odb)
source $::env(SCRIPTS_DIR)/load.tcl
set stage [expr { [info exists ::env(PROBE_STAGE)] ? $::env(PROBE_STAGE) : "5_1_grt.odb" }]
load_design $stage
estimate_parasitics -global_routing
set min_um [expr { [info exists ::env(PROBE_MIN_UM)] ? $::env(PROBE_MIN_UM) : 20.0 }]
set ui_ps [expr { [sta::time_ui_sta 1.0] * 1e12 }]
set dbu [[ord::get_db_block] getDbUnitsPerMicron]
set out [open $::env(PROBE_OUT) w]

proc arrival { p } {
  set best ""
  foreach rf {arrival_max_rise arrival_max_fall} {
    set a [get_property $p $rf]
    if { [string is double -strict $a] && abs($a) < 1e20 } {
      if { $best eq "" || $a > $best } { set best $a }
    }
  }
  return $best
}

set n 0
foreach net [[ord::get_db_block] getNets] {
  if { [$net getSigType] ne "SIGNAL" } { continue }
  set drv ""
  set loads {}
  foreach it [$net getITerms] {
    if { [$it isOutputSignal] } { set drv $it } elseif { [$it isInputSignal] } { lappend loads $it }
  }
  if { $drv eq "" || [llength $loads] == 0 } { continue }
  lassign [$drv getAvgXY] ok dx dy
  if { !$ok } { continue }
  set far ""
  set far_d 0
  foreach it $loads {
    lassign [$it getAvgXY] ok lx ly
    if { !$ok } { continue }
    set d [expr { abs($lx - $dx) + abs($ly - $dy) }]
    if { $d > $far_d } { set far_d $d; set far $it }
  }
  set um [expr { double($far_d) / $dbu }]
  if { $far eq "" || $um < $min_um } { continue }
  set dp [get_pins -quiet "[[$drv getInst] getName]/[[$drv getMTerm] getName]"]
  set lp [get_pins -quiet "[[$far getInst] getName]/[[$far getMTerm] getName]"]
  if { [llength $dp] != 1 || [llength $lp] != 1 } { continue }
  set a0 [arrival $dp]
  set a1 [arrival $lp]
  if { $a0 eq "" || $a1 eq "" } { continue }
  set ps [expr { ($a1 - $a0) * $ui_ps }]
  puts $out "[format %.2f $um] [format %.2f $ps] [format %.4f [expr { $ps / $um }]] [$net getName]"
  incr n
}
close $out
puts "probe_wire: $n spans of at least $min_um um written to $::env(PROBE_OUT)"
