# The generated register file as a block: a clock on its one clock port
# and set_max_delay budgets on the paths through its pins. No
# set_input_delay or set_output_delay: the insertion latency at a block's
# clock pin is the parent's CTS to decide, not a number to assert here.
set clk_period 1200
create_clock -period $clk_period -name clock [get_ports clock]

set non_clk_inputs [all_inputs -no_clocks]
set in2reg_max  [expr { $clk_period * 0.8 }]
set reg2out_max [expr { $clk_period * 0.8 }]
set in2out_max  [expr { $clk_period * 0.6 }]

set_max_delay $in2out_max -from $non_clk_inputs -to [all_outputs]
group_path -name in2out -from $non_clk_inputs -to [all_outputs]
set_max_delay $in2reg_max -from $non_clk_inputs -to [all_registers]
group_path -name in2reg -from $non_clk_inputs -to [all_registers]
set_max_delay $reg2out_max -from [all_registers] -to [all_outputs]
group_path -name reg2out -from [all_registers] -to [all_outputs]
group_path -name reg2reg -from [all_registers] -to [all_registers]
