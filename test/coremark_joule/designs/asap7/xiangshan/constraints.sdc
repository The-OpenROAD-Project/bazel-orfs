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

# The IO budget, as optimization targets. set_input_delay and
# set_output_delay are deliberately not used anywhere in this study:
# see §3.8 of the paper, which is where the model is argued.
#
# The short form is that a CPU core's frequency is set by its
# register-to-register paths and by nothing else, because the thing on
# the other side of its pins is a clock-crossing bridge, a bus register
# or a GPIO pad -- something that terminates the path rather than
# continuing it. So assume a register immediately outside every port.
# For XSCore that thing is literally a register: every port of the
# boundary is a TileLink channel into the L2, a sibling inside XSTile.
#
# $PLATFORM_DIR/constraints.sdc implements exactly that with
# set_max_delay, and defaults each budget to 80 ps when the design says
# nothing -- a figure written for a small macro, and an impossible
# target on a CPU. An optimiser chasing an impossible target upsizes
# cells and inserts buffers whose power is then charged to the core.
#
# The ratios are ORFS's own, from its asap7/swerv_wrapper: 0.8 of the
# period for a path with a register at one end, leaving 0.2 for the
# clock-to-q and setup of the register assumed outside, and 0.6 for a
# combinational path straight through.
set in2reg_max  [expr { $clk_period * 0.8 }]
set reg2out_max [expr { $clk_period * 0.8 }]
set in2out_max  [expr { $clk_period * 0.6 }]

source $::env(PLATFORM_DIR)/constraints.sdc
