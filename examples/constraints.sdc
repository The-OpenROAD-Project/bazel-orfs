# 1 GHz clock on the single clock port. asap7 units are picoseconds.
create_clock -period 1000 -name clk [get_ports clk]

# I/O budgets as optimization targets, not as set_input_delay /
# set_output_delay.
#
# The only paths that can *fail* timing closure are register to register.
# Everything touching a port -- in-to-reg, reg-to-out, in-to-out -- is a
# target that tells the tools how hard to work, and a macro's real
# environment decides whether it mattered. asap7's own
# platforms/asap7/constraints.sdc makes this argument at length and is
# worth reading before writing constraints of your own.
#
# Two concrete reasons not to reach for set_input_delay here:
#
#   It cannot be written down honestly. The number it takes is measured
#   from the clock insertion point, so choosing one means assuming a
#   clock tree that does not exist yet -- and being wrong about it
#   silently over- or under-constrains every input path.
#
#   It demands hold fixing on every I/O path. A set_input_delay the
#   design's environment does not actually impose still buys a crop of
#   hold buffers, which cost area and leakage for nothing.
#
# set_max_delay -ignore_clock_latency has neither problem. The budgets
# below leave 20% of the period for whatever is on the other side of the
# pin, and 40% for a combinational path that crosses the block entirely.
set non_clk_inputs [all_inputs -no_clocks]

set_max_delay -ignore_clock_latency 800 -from $non_clk_inputs -to [all_registers]
set_max_delay -ignore_clock_latency 800 -from [all_registers] -to [all_outputs]
set_max_delay 600 -from $non_clk_inputs -to [all_outputs]

# Separate the groups so a report says which kind of path is tight.
group_path -name in2reg -from $non_clk_inputs -to [all_registers]
group_path -name reg2out -from [all_registers] -to [all_outputs]
group_path -name reg2reg -from [all_registers] -to [all_registers]
group_path -name in2out -from $non_clk_inputs -to [all_outputs]
