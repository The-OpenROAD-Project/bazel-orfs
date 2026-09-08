set clk_name core_clock
set clk_port_name clk
# Picoseconds, like every asap7 SDC in tree. The platform's constraints
# file turns these into create_clock; passing a period through anything
# that reports STA-internal units instead would produce a near-zero
# clock, which reads as a very slow design rather than as a mistake.
set clk_period [expr { [info exists ::env(WIREBOUND_CLK_PERIOD_PS)]
                       && $::env(WIREBOUND_CLK_PERIOD_PS) ne ""
                       ? $::env(WIREBOUND_CLK_PERIOD_PS) : 1000 }]

source $env(PLATFORM_DIR)/constraints.sdc
