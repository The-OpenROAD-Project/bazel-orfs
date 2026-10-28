# The toy Rob's QoR at a stage, as JSON: the clock's minimum period, the
# endpoints over the target period with their total excess, cell area,
# cells and flops. Every path starts and ends at a register of the
# toy's top, so the period is the structure's.
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)
source $::env(PLATFORM_DIR)/setRC.tcl
estimate_parasitics -placement
set clk [lindex [all_clocks] 0]
set period [sta::find_clk_min_period $clk 0]
set area 0
set cells 0
set flops 0
foreach inst [[ord::get_db_block] getInsts] {
  set master [$inst getMaster]
  if { [$master getType] eq "CORE" } {
    set area [expr { $area + [$master getWidth] * [$master getHeight] }]
    incr cells
    if { [$master isSequential] } {
      incr flops
    }
  }
}
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"period_ps\": [format %.1f [expr { $period * 1e12 }]],"
puts $out "  \"over_target\": [sta::endpoint_violation_count max],"
puts $out "  \"excess_ps\": [format %.0f [expr { -[sta::total_negative_slack_cmd max] * 1e12 }]],"
puts $out "  \"area_um2\": [format %.2f [expr { double($area) / $dbu / $dbu }]],"
puts $out "  \"cells\": $cells,"
puts $out "  \"flops\": $flops"
puts $out "}"
close $out
