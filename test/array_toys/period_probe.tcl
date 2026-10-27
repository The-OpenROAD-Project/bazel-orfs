# A toy's register-to-register period and cell area at a stage, as JSON.
# Every path through the structure starts and ends at a register of the
# toy's top, so the clock's minimum period without port paths is the
# structure's.
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)
set clk [lindex [all_clocks] 0]
set period [sta::find_clk_min_period $clk 0]
set area 0
set cells 0
foreach inst [[ord::get_db_block] getInsts] {
  set master [$inst getMaster]
  if { [$master getType] eq "CORE" || [$master getType] eq "BLOCK" } {
    set area [expr { $area + [$master getWidth] * [$master getHeight] }]
    incr cells
  }
}
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"period_ps\": [format %.1f [expr { $period * 1e12 }]],"
puts $out "  \"area_um2\": [format %.2f [expr { double($area) / $dbu / $dbu }]],"
puts $out "  \"cells\": $cells"
puts $out "}"
close $out
