# 1 GHz clock on the single clock port. asap7 units are picoseconds.
create_clock -period 1000 -name clk [get_ports clk]

# Give the inputs and outputs a plausible external budget so the
# in-to-reg and reg-to-out paths are constrained too.
set_input_delay  200 -clock clk [all_inputs -no_clocks]
set_output_delay 200 -clock clk [all_outputs]
