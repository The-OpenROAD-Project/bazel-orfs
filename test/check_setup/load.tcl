# The design the test names, with a clock on clk.
foreach lef $::env(LEFS) {
  read_lef $lef
}
foreach lib $::env(LIBS) {
  read_liberty $lib
}
read_verilog $::env(VERILOG)
link_design top
create_clock -name clk -period 1000 [get_ports clk]

# The pins check_setup calls unclocked registers.
proc unclocked_pins {} {
  # no_input_delay no_output_delay multiple_clock no_clock unconstrained
  # loops generated_clocks: only the unclocked-register check
  set pins {}
  foreach error [sta::check_timing_cmd 0 0 0 1 0 0 0] {
    puts [join $error "\n  "]
    lappend pins {*}[lrange $error 1 end]
  }
  return $pins
}

# The pins check_setup names under each of its port and endpoint
# warnings, as a dict from the warning to its pins.
proc constraint_warnings {} {
  set warnings {}
  foreach error [sta::check_timing_cmd 1 1 0 0 1 0 0] {
    puts [join $error "\n  "]
    dict set warnings [lindex $error 0] [lrange $error 1 end]
  }
  return $warnings
}
