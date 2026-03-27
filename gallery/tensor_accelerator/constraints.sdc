# 1000ps = 1 GHz target for ASAP7
#
# Inlines the platform SDC because gutted designs (SYNTH_GUT=1 from
# mock_area) have no registers, causing STA-0391 with the platform's
# unguarded group_path calls.

set clk_name      clk
set clk_port_name clk
set clk_period    1000

set sdc_version 2.0

set clk_port [get_ports $clk_port_name]
create_clock -period $clk_period -waveform [list 0 [expr $clk_period / 2]] -name $clk_name $clk_port

set non_clk_inputs [all_inputs -no_clocks]

set_max_delay -ignore_clock_latency \
  [expr { [info exists in2reg_max] ? $in2reg_max : 80 }] -from $non_clk_inputs \
  -to [all_registers]
set_max_delay -ignore_clock_latency \
  [expr { [info exists reg2out_max] ? $reg2out_max : 80 }] -from [all_registers] \
  -to [all_outputs]
set_max_delay [expr { [info exists in2out_max] ? $in2out_max : 80 }] -from $non_clk_inputs \
  -to [all_outputs]

# Guard group_path — gutted designs (mock_area) have no registers
if {[llength [all_registers]] > 0} {
    group_path -name in2reg -from $non_clk_inputs -to [all_registers]
    group_path -name reg2out -from [all_registers] -to [all_outputs]
    group_path -name reg2reg -from [all_registers] -to [all_registers]
}
if {[llength $non_clk_inputs] > 0 && [llength [all_outputs]] > 0} {
    group_path -name in2out -from $non_clk_inputs -to [all_outputs]
}
