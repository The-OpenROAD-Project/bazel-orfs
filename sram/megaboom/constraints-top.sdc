set clk_name clock
set clk_port_name clock
set clk_period 50

set in2reg_max 160
set reg2out_max 50
set in2out_max 350

if { [llength [all_registers]] > 0} {
  source $env(PLATFORM_DIR)/constraints.sdc
} else {
  puts "The design is gutted when mocking floorplan"
}
