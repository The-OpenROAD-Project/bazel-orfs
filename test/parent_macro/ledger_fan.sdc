# ledger_fan's clock, and its inputs' budgets in two groups, as a part's
# SDC has a budget per port: each group's set_max_delay to the registers
# and to the outputs is an exception of its own, and a path carries the
# state of every one its input starts, so two paths into one output from
# the two groups carry different exception states.
create_clock -name clock -period 1000 [get_ports clock]
set_max_delay -ignore_clock_latency 300 -from [get_ports {a[0] a[2] b}] -to [all_registers]
set_max_delay -ignore_clock_latency 400 -from [get_ports {a[1] a[3] c d}] -to [all_registers]
set_max_delay 300 -from [get_ports {a[0] a[2] b}] -to [all_outputs]
set_max_delay 400 -from [get_ports {a[1] a[3] c}] -to [all_outputs]
