# 1000ps = 1 GHz — clock for SRAM macros on ASAP7
# Uses 'clock' (the SRAM port name) instead of 'aclk' (CoreMiniAxi's AXI clock).
# Does NOT source platform constraints.sdc because group_path fails on
# gutted designs (SYNTH_GUT=1 removes all registers → STA-0391).
set clk_name  clock
set clk_port_name clock
set clk_period 1000

create_clock [get_ports $clk_port_name] -name $clk_name -period $clk_period
