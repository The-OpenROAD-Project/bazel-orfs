# a 70 ps clock, below the loop's hand-result floor, so every endpoint,
# the loop's among them, violates and timing repair has to act on the loop
# reg2reg only: the loops are what is measured, and IO delays on inputs that
# feed flops directly would only make hold repair fill the design with
# delay buffers (RSZ-0060 at CTS when they were here)
create_clock -name clk -period 70 [get_ports clk]
# the cap XiangShan's SDC sets
set_max_fanout 32 [current_design]
