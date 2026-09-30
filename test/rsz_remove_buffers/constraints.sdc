set clk_name clk
set clk_port_name clock
set clk_period 473
create_clock -name $clk_name -period $clk_period [get_ports $clk_port_name]
set_max_fanout 32 [current_design]
