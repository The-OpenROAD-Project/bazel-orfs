# The Rob's QoR at a stage, as JSON: the register-to-register minimum
# period (port paths are set_max_delay budgets, which a macro's
# closure does not rest on), the reg2reg endpoints over the clock period
# with their total excess, cell area, cells and flops.
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)
source $::env(PLATFORM_DIR)/setRC.tcl
estimate_parasitics -placement
set clk [lindex [all_clocks] 0]
set period [sta::find_clk_min_period $clk 1]
set over 0
set excess 0.0
foreach path [find_timing_paths -path_group reg2reg -group_path_count 1000000 -endpoint_path_count 1 -slack_max 0] {
  incr over
  set excess [expr { $excess - [get_property $path slack] }]
}
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
puts $out "  \"reg2reg_over_target\": $over,"
puts $out "  \"reg2reg_excess_ps\": [format %.0f [expr { $excess * 1e12 }]],"
puts $out "  \"area_um2\": [format %.2f [expr { double($area) / $dbu / $dbu }]],"
puts $out "  \"cells\": $cells,"
puts $out "  \"flops\": $flops"
puts $out "}"
close $out
