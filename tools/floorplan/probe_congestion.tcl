# The judge of the planner's channel verdict: a zero-iteration global
# route with congestion allowed on a placed parent (test/macro_select's
# route-0), its congestion report (FastRoute's regions over capacity,
# each a box and a layer) and the parent's macro outlines, for
# judge.py to name each region's channel or macro side.
#
#   PROBE_STAGE       the ODB (4_cts.odb)
#   CONGESTION_REPORT the congestion report to write
#   PROBE_OUT         the macros, one per line: <inst> <master> x0 y0 x1 y1 (um)
source $::env(SCRIPTS_DIR)/load.tcl
load_design [expr { [info exists ::env(PROBE_STAGE)] ? $::env(PROBE_STAGE) : "4_cts.odb" }]
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set out [open $::env(PROBE_OUT) w]
set die [$block getDieArea]
puts $out "die [expr { [$die xMax] / double($dbu) }] [expr { [$die yMax] / double($dbu) }]"
foreach inst [$block getInsts] {
  if { ![[$inst getMaster] isBlock] } { continue }
  set b [$inst getBBox]
  puts $out "macro [$inst getName] [[$inst getMaster] getName] [expr { [$b xMin] / double($dbu) }] [expr { [$b yMin] / double($dbu) }] [expr { [$b xMax] / double($dbu) }] [expr { [$b yMax] / double($dbu) }]"
}
close $out
set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
if { [info exists ::env(ROUTING_LAYER_ADJUSTMENT)] } {
  set_global_routing_layer_adjustment $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER) $::env(ROUTING_LAYER_ADJUSTMENT)
}
global_route -congestion_iterations 0 -allow_congestion -verbose -congestion_report_file $::env(CONGESTION_REPORT)
if { ![file exists $::env(CONGESTION_REPORT)] } {
  set f [open $::env(CONGESTION_REPORT) w]
  close $f
}
