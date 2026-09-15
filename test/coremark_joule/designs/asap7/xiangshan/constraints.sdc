# A starting period, not a result.
#
# The study's frequency comes from a sweep over clock periods at global
# route, taking f = 1 / (period - WNS) at a slightly negative WNS. This
# value only has to be close enough that the first sweep point is useful.
#
# 1200 ps is the same starting point the other three cores use. XiangShan
# is a far deeper design and will not close there; that is what the sweep
# is for, and starting every core at the same period keeps the first
# measurement comparable rather than pre-tuned.
set clk_name clk
set clk_port_name clock
set clk_period 1200

source $::env(PLATFORM_DIR)/constraints.sdc
