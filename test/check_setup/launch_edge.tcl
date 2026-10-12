# Only the falling edge of the clock reaches a rising-edge flop: no path
# through it is timed, and check_setup says so: patches/0109. Before it,
# the flop was in the clock network, which ignores transitions, and
# check_setup said nothing.
source [file join [file dirname [info script]] load.tcl]

set unclocked [unclocked_pins]
if { [lsearch -exact $unclocked r/CLK] < 0 } {
  puts "FAIL: r/CLK not reported unclocked"
  exit 1
}
puts "PASS"
