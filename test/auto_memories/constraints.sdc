# A clock and nothing else. This design exists to exercise
# AUTO_MEMORIES' plumbing, not to close timing.
create_clock -name clk -period 2000 [get_ports clk]
