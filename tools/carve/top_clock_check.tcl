# The flat top level's clock after CTS (parent_macro.bzl, POST_CTS_TCL):
# every register of every dissolved macro clocked from the clock port,
# through the clock gates the macros kept, and the one tree CTS built over
# them within MAX_SKEW_PS. Either one failing stops the top level here.
set registers [llength [all_registers]]
set clocked [llength [all_registers -clock [all_clocks]]]
if { $clocked != $registers } {
  utl::error FLW 25 "top_clock_check: [expr { $registers - $clocked }] of $registers registers have no clock"
}
set skew [expr { abs([worst_clock_skew -setup]) }]
puts "top_clock_check: $registers registers clocked, setup skew $skew"
if { $skew > $::env(MAX_SKEW_PS) } {
  utl::error FLW 26 "top_clock_check: setup skew $skew ps over $::env(MAX_SKEW_PS) ps"
}
