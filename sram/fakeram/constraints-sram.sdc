set clk_name clk
set clk_port_name clk
set clk_period 400

if { [llength [all_registers]] > 0} {
  source $env(PLATFORM_DIR)/constraints.sdc
} else {
  puts "The design is gutted when mocking floorplan"
}
