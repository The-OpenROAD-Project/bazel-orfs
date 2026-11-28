# reg2reg only, as test/fanout_loop: the multiplier between the last
# empty stage and the output register is what is measured.
create_clock -name clk -period 250 [get_ports clk]
