# Let the well-informed repair decide which buffers to remove.
#
# The companion to grt_unbuffer.tcl. That one removes every signal
# buffer before global route; this one removes none and instead adds
# `unbuffer` to the move sequence the global-route repair is allowed to
# use, so the resizer takes buffers out only where its own -- accurate
# -- parasitics say they are not earning their place.
#
# Set here rather than as an ORFS variable because SETUP_MOVE_SEQUENCE
# is read by repair_timing_helper at every call site, so passing it
# through the build would change the CTS repair too and the arm would
# vary two things at once. PRE_GLOBAL_ROUTE_TCL runs inside
# global_route.tcl, after the CTS repair has already happened and
# before the global-route one, which makes the override stage-scoped by
# construction.
#
# The sequence is floorplan.tcl's own, which is the flow's existing
# statement of what a sequence including unbuffer should look like
# rather than one invented here.

set ::env(SETUP_MOVE_SEQUENCE) "unbuffer,sizeup,swap,vt_swap"

puts "GRT_UNBUFFER_SEQ SETUP_MOVE_SEQUENCE=$::env(SETUP_MOVE_SEQUENCE)"
