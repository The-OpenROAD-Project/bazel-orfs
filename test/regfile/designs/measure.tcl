# One arm's routed design, measured as ORFS's final report does, as JSON:
# the clock period the SDC sets, setup WNS after RCX extraction, the
# minimum period (period - WNS), the same for register-to-register paths
# alone (a boundary path can set the first and say nothing about the
# core), standard-cell area and cell count; and report_power's JSON
# beside it (POWER_JSON).
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)
source_env_var_if_exists SET_RC_TCL
define_process_corner -ext_model_index 0 X
set_extraction_rules_file $::env(RCX_RULES)
extract_parasitics
set spef [file rootname $::env(OUTPUT_JSON)].spef
write_spef $spef
read_spef $spef

set block [ord::get_db_block]
set u [$block getDbUnitsPerMicron]
set area 0.0
set cells 0
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set type [$m getType]
  if { [$m isBlock] || [string match *WELLTAP $type] || [string match *SPACER $type]
       || [string match *ENDCAP* $type] || [string match TAPCELL* [$m getName]] } {
    continue
  }
  set area [expr { $area + double([$m getWidth]) * [$m getHeight] / $u / $u }]
  incr cells
}
set clocks [all_clocks]
if { [llength $clocks] == 0 } {
  error "measure: no clock"
}
set period [get_property [lindex $clocks 0] period]
set wns [sta::time_sta_ui [sta::worst_slack_cmd "max"]]
set r2r [find_timing_paths -from [all_registers] -to [all_registers] \
  -path_delay max -group_path_count 1 -sort_by_slack]
if { [llength $r2r] == 0 } {
  error "measure: no register-to-register path"
}
set r2r_slack [get_property [lindex $r2r 0] slack]
report_power -format json > $::env(POWER_JSON)
set out [open $::env(OUTPUT_JSON) w]
puts $out [format {{"period_ps": %.1f, "wns_ps": %.1f, "min_period_ps": %.1f, "reg2reg_min_period_ps": %.1f, "stdcell_um2": %.2f, "cells": %d}} \
  $period $wns [expr { $period - $wns }] [expr { $period - $r2r_slack }] $area $cells]
close $out
