# The platform's constraints for a macro, every macro of tpu and flat
# alike: one clock, the boundary as set_max_delay targets. CLK_PERIOD is
# the period repair aims at, 450 ps unless a flow sets it; the period
# read is the design's either way, the clock minus the worst reg2reg
# slack.
set clk_name core_clock
set clk_port_name clk
set clk_period [expr { [info exists ::env(CLK_PERIOD)] ? $::env(CLK_PERIOD) : 450 }]
set in2reg_max 300
set reg2out_max 100
set in2out_max 100
source $env(PLATFORM_DIR)/constraints.sdc
