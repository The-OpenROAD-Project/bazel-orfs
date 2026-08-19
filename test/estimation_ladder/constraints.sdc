current_design multiplier
create_clock [get_ports clk] -name core_clock -period 1.000
set_input_delay -clock core_clock 0.200 [get_ports {valid_in a[*] b[*]}]
set_output_delay -clock core_clock 0.200 [get_ports {valid_out product[*]}]
