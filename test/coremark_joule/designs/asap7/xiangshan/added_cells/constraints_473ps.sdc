# Tight 473 ps SDC (XiangShan's 333 ps 7 nm goal in ASAP7 FO4, matching KPI
# runs 2..35) so ABC speed mapping and OpenROAD CTS/GRT repair_timing push to
# FltRegionModule's actual minimum period (~1,027 ps, negative slack) rather
# than stopping early with +532 ps positive slack under the 1,800 ps tile SDC.
set clk_name clk
set clk_port_name clock
set clk_period 473

set in2reg_max  378.4
set reg2out_max 378.4
set in2out_max  283.8

foreach p [get_ports -quiet reset] {
  set_false_path -from $p
}

set_max_fanout 32 [current_design]

if { [llength [all_registers]] > 0 } {
  source $::env(PLATFORM_DIR)/constraints.sdc
}
