# 1,800 ps: just under what the tile reaches, chosen as the study chooses
# every core's (test/coremark_joule/README.md, §5.7): the SDC asks for
# what the design reaches, period minus reg2reg WNS. Built with the SDC
# at 473 ps (2026-11-21), XSTile's parent reached a reg2reg period of
# 1,822 ps at global route (blocks: MemBlock 1,066, Frontend 1,062,
# FltRegionModule 1,027, VecRegionModule 975, CoupledL2 864). Just under
# it, repair works right up to the limit and the build ends with a
# slightly negative WNS, tens of ps, instead of stopping early with
# slack, so power is measured near timing closure, not on a netlist
# repaired against a period it misses by more than a nanosecond. One
# step of auto_period's walk, taken by hand: each step is a day-long
# build of the tile. The campaign's goal, 2,000 ps (kpi.py's GOAL_PS),
# is not the SDC. Every
# XiangShan flow reads this file, the blocks and register files with the
# parent; each block's own reg2reg period is below it.
#
# XiangShan's published goal, 333 ps on 7 nm, is 591 ps at global route
# on this library in fanouts of four: kpi.json's target_ps, which
# period_fo4_test checks.
set clk_name clk
set clk_port_name clock
set clk_period 1800

# The IO budget, as optimization targets. set_input_delay and
# set_output_delay are deliberately not used anywhere in this study:
# see §3.8 of the paper, which is where the model is argued.
#
# The short form is that a CPU core's frequency is set by its
# register-to-register paths and by nothing else, because the thing on
# the other side of its pins is a clock-crossing bridge, a bus register
# or a GPIO pad -- something that terminates the path rather than
# continuing it. So assume a register immediately outside every port.
# For XSTile that thing is the asynchronous crossing in XSTileWrap,
# immediately outside it -- the CHI bridge, the CLINT time queue, the
# reset synchronisers -- which registers every signal it takes.
#
# $PLATFORM_DIR/constraints.sdc implements exactly that with
# set_max_delay, and defaults each budget to 80 ps when the design says
# nothing -- a figure written for a small macro, and an impossible
# target on a CPU. An optimiser chasing an impossible target upsizes
# cells and inserts buffers whose power is then charged to the core.
#
# The budgets are picoseconds, deliberately not a fraction of the clock
# period. Every flow reads them, XSTile and each hardened block alike: in
# a block they are its side of a path that crosses into the parent or
# another block, and the parent times the whole crossing through the
# block's abstract, where it cannot repair. The tile's period is set by
# such crossings, so the budgets stay at the values its crossings were
# measured with when its parent reached 1,822 ps: 378.4 ps for a path
# with a register at one end, 283.8 ps for one straight through (0.8 and 0.6 of
# 473 ps, ORFS's ratios from its asap7/swerv_wrapper). Two block sides at
# 0.8 of 1,800 ps would sum to 2,880 ps, past the period they are meant
# to fit (.claude/skills/macro-constraints, "When the budgets do look
# wrong").
set in2reg_max  378.4
set reg2out_max 378.4
set in2out_max  283.8

# Reset is a false path here. XiangShan's reset is asynchronous -- 1005 of
# XSCore's always blocks are `posedge clock or posedge reset` -- and the one
# `reset` port reaches the async-reset pin of every one of those flops.
# Timed, that is a recovery and removal check at every flop against the
# arrival through a buffer tree the flow builds for the net, and
# repair_timing at every stage would fight it. A chip de-asserts such a
# reset through a synchroniser and lets the tree settle; the check is
# not what sets the core's frequency. repair_design still buffers the
# net for slew and load, as a real reset tree is.
foreach p [get_ports -quiet reset] {
  set_false_path -from $p
}

# CoupledL2's data SRAMs are read over two cycles, as the RTL states:
# XSCache's DataStorage.scala builds them with readMCP2 = true ("read
# data is set MultiCycle Path 2 ... s3 read, s4 pass and s5 to
# destination"), holds the request for two cycles and asserts that no
# request follows another ("Continuous SRAM req prohibited under
# MCP2!"). The constraint is the designers' contract, not an exception
# made for a tool. It covers what the SRAM launches only: the request and
# write data reach the SRAM at the next edge of its gated clock, one
# cycle, and stay single-cycle paths. In the parent, where CoupledL2 is
# a macro, nothing matches.
foreach c [get_cells -quiet -hierarchical \
             -filter "full_name =~ *dataStorage.array.*array_ext" *] {
  set_multicycle_path -setup 2 -from $c
  set_multicycle_path -hold 1 -from $c
}

# A fanout cap for the resizer. Without one, broadcast nets -- valids,
# enables, decoded control -- come out of repair_design as long serial
# repeater chains that global route then has to carry. 32 is a starting
# point, textbook order of magnitude; the right value is a sweep against
# the PDK's max_transition, and this one has not been swept.
set_max_fanout 32 [current_design]

# The platform's constraints add group_path targets between inputs,
# registers and outputs. VectorDecodeChannel, a block of this design, is
# pure decode with no register, and group_path refuses an empty -from or
# -to (STA-0391); a design without registers has no such groups to name.
if { [llength [all_registers]] > 0 } {
  source $::env(PLATFORM_DIR)/constraints.sdc
}
