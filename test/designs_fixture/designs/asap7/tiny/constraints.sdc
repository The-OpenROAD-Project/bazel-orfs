# A clock and nothing else: this design exists to be discovered, not to
# close timing.
create_clock -name clk -period 2000 [get_ports clk]
