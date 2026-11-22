# The toy's one clock, on both of the clock ports BlockB's flow has.
set clk_name clock
set clk_period 1000
create_clock -name $clk_name -period $clk_period [get_ports {clock clock_ext}]
