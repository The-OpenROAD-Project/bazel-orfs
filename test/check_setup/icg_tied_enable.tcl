# A flop behind an ICG whose enable is tied high is clocked through the
# gate and timed: parallaxsw/OpenSTA@fdb00f4. Before it, the conditioned CLK->GCLK
# arc set (falling edge only) disabled the rising default arc, and
# report_checks -to r/D found no path.
source [file join [file dirname [info script]] load.tcl]
set_input_delay 0 -clock clk [get_ports d]

set unclocked [unclocked_pins]
set paths [find_timing_paths -to [get_pins r/D] -path_delay max]
if { [llength $paths] == 0 } {
  puts "FAIL: no timed path to r/D"
  exit 1
}
if { [llength $unclocked] != 0 } {
  puts "FAIL: unclocked register pins: $unclocked"
  exit 1
}
puts "PASS"
