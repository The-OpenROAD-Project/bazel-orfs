# 800 ps: the synthesis target for a core that should route at 1000 ps.
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
set clk_period 800

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
# The ratios are ORFS's own, from its asap7/swerv_wrapper: 0.8 of the
# period for a path with a register at one end, leaving 0.2 for the
# clock-to-q and setup of the register assumed outside, and 0.6 for a
# combinational path straight through.
set in2reg_max  [expr { $clk_period * 0.8 }]
set reg2out_max [expr { $clk_period * 0.8 }]
set in2out_max  [expr { $clk_period * 0.6 }]

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

# A fanout cap for the resizer. Without one, broadcast nets -- valids,
# enables, decoded control -- come out of repair_design as long serial
# repeater chains that global route then has to carry. 32 is a starting
# point, textbook order of magnitude; the right value is a sweep against
# the PDK's max_transition, and this one has not been swept.
set_max_fanout 32 [current_design]

# The L2's data banks are read in two cycles (CoupledL2 DataStorage,
# readMCP2): the request is held for two cycles and the data is sampled
# two cycles later, so every path into and out of a bank has two periods.
# Timed as one, each read looks like a violation the design never has.
# The banks are only in CoupledL2's flow; there, finding none means the
# constraint has lost its target, and that is an error rather than a
# clean report.
set l2_data_banks [get_cells -quiet -hierarchical * -filter "ref_name == array_8192x137"]
if { [llength $l2_data_banks] > 0 } {
  set_multicycle_path 2 -setup -to $l2_data_banks
  set_multicycle_path 1 -hold -to $l2_data_banks
  set_multicycle_path 2 -setup -from $l2_data_banks
  set_multicycle_path 1 -hold -from $l2_data_banks
} elseif { [info exists ::env(DESIGN_NAME)] && $::env(DESIGN_NAME) eq "CoupledL2" } {
  error "constraints_800ps.sdc: no array_8192x137 in CoupledL2, the L2 data banks' multicycle path has no target"
}

# The platform's constraints add group_path targets between inputs,
# registers and outputs. VectorDecodeChannel, a block of this design, is
# pure decode with no register, and group_path refuses an empty -from or
# -to (STA-0391); a design without registers has no such groups to name.
if { [llength [all_registers]] > 0 } {
  source $::env(PLATFORM_DIR)/constraints.sdc
}
