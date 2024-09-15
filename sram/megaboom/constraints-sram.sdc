set clk_name R0_clk
set clk_port_name R0_clk
set clk_period 400

if { [llength [all_registers]] > 0} {
  source $env(PLATFORM_DIR)/constraints.sdc
} else {
  puts "The design is gutted when mocking floorplan"
}

create_clock -period $clk_period -name W0_clk [get_ports W0_clk]
