# a 100 ps clock, so the loop violates and timing repair acts on it
# reg2reg only: the loops are what is measured, and IO delays on inputs that
# feed flops directly would only make hold repair fill the design with
# delay buffers (RSZ-0060 at CTS when they were here)
create_clock -name clk -period 100 [get_ports clk]
# the cap XiangShan's SDC sets
set_max_fanout 32 [current_design]
