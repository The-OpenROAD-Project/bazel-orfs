# 1000ps = 1 GHz — AXI clock for CoreMiniAxi on ASAP7
# Port is io_aclk after Chisel lowering (Chisel adds io_ prefix to top-level ports)
set clk_name  io_aclk
set clk_port_name io_aclk
set clk_period 1000

source $::env(PLATFORM_DIR)/constraints.sdc
