# wirebound: the congested, top-metal, wire-delay-dominated corner that
# no asap7 design in ORFS occupies. See wirebound.sv for why.
#
# MAX_ROUTING_LAYER is the point of the design and is deliberately not
# the platform default. asap7 ships MAX_ROUTING_LAYER ?= M7 against a
# nine-metal stack, so M8 and M9 -- the two least resistive layers, ~8x
# below M1 -- are unreachable for every design in the tree. A design that
# cannot route on them cannot show what mispricing them costs.
export PLATFORM               = asap7
export DESIGN_NAME            = wirebound
export DESIGN_NICKNAME        = wirebound

export VERILOG_FILES          = $(DESIGN_HOME)/asap7/wirebound/wirebound.sv
export SDC_FILE               = $(DESIGN_HOME)/asap7/wirebound/constraint.sdc

export MAX_ROUTING_LAYER      = M9

# The clock target, as a variable so a study arm can move it. A repair
# measurement is only valid if the baseline has something to repair: a
# design that closes reports clean zero deltas for every knob, which is
# indistinguishable from a knob that does nothing. Read back and asserted
# in the measurement scripts rather than trusted.
export WIREBOUND_CLK_PERIOD_PS = 1000

# Last gasp is the long tail of repair_timing and there is no reason to
# expect a min_period cliff in it, so it buys runtime here rather than
# insight. Off, deliberately, on a design whose whole value is a short
# edit/measure loop.
export SKIP_LAST_GASP = 1

# Derived from the synthesized area rather than pinned, so a change to
# GROUPS re-shapes the die instead of silently changing utilization.
export CORE_UTILIZATION       = 55
export CORE_MARGIN            = 2
export PLACE_DENSITY          = 0.60
