set clk_name clk
set clk_port_name clk
set clk_period 300
set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port
