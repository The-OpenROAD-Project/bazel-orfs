set clk_name clock
set clk_port_name clock
set clk_period 1000
set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port
