# The top level of a parent macro (parent_macro.bzl) cut down to what a
# register-to-register path between macros can touch, so the crossing
# report (crossing_paths.tcl) times a fraction of the design: XSTile's
# routed top level ran out of memory timed whole. Sourced by
# top_level.tcl before timing.
#
# A macro is an instance name's first level (u_parent, u_Bpu, ...); the
# top level's own cells, the clock tree, have none. Kept:
#
#   every net with cells of two macros on it, where one of them is in
#   CONE_MACROS (all of them when it is "all"); the parent, on every such
#   net, need not be listed: a set names its blocks. From each, the logic
#   forward through loads and backward through drivers to the first
#   register, latch, clock gate, memory or macro, through the set's
#   blocks, the parent and the top level; a cell of any other block is
#   kept as a load and goes no further, so a path between two blocks is
#   timed only in a set that holds both;
#   the fan-in of every side input of a forward cell, backward only: an
#   output's slew is its worst input arc's;
#   every cell on a kept net, so each driver keeps its load;
#   the clock network into every kept register, every cell on it kept as
#   a load so each latency is the whole design's.
#
# On the toy (test/parent_macro) at 150 ps, cut to every boundary (29 %
# of its instances) or to the sets {BlockA BlockB} {BlockC} {BlockD}, the
# crossing report is the whole design's, path for path and slack for
# slack.
#
# Everything else is deleted, generated arrays' dont_touch cells
# included: the design is only timed from here on. The search is
# OpenROAD's crossing_cones (dbSta.i in the carve's OpenROAD); in Tcl it
# spent minutes in SWIG per million nets.
set parent [env_var_or_empty PARENT_INST]
if { $parent eq "" } {
  set parent u_parent
}
set needs [lassign [sta::crossing_cones $::env(CONE_MACROS) $parent 0] seeds kept before]
puts "crossing_cones: $seeds crossing nets, $kept of $before instances kept ($::env(CONE_MACROS))"
if { [llength $needs] } {
  # a path into these blocks has a signature another set holds
  # (crossing_plan.tcl): cut here at their first cell, it ends at none
  puts "crossing_cones: cones stop at [join $needs { }]"
}
