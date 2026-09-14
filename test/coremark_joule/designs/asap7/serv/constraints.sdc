# A starting period, not a result.
#
# The study's frequency comes from an orfs_sweep over clock periods at
# global route, taking f = 1 / (period - WNS) at a slightly negative WNS.
# This value only has to be close enough that the first sweep point is
# useful.
set clk_name clk
set clk_port_name clk
set clk_period 700

source $::env(PLATFORM_DIR)/constraints.sdc
