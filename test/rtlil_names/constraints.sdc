# A clock and nothing else: this design exists to exercise module-name
# resolution, not to close timing.
create_clock -name clk -period 2000 [get_ports clk]
