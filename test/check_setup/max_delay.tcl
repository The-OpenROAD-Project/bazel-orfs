# A port a set_max_delay names is constrained, and so is a register a
# set_max_delay reaches from it: patches/0110. Before it, check_setup
# said d was missing set_input_delay, q set_output_delay, and r/D was an
# unconstrained endpoint. e, p and u/D have no constraint at all and
# must still be named.
source [file join [file dirname [info script]] load.tcl]
set_max_delay 800 -from [get_ports d] -to [get_cells r]
set_max_delay 800 -from [get_cells r] -to [get_ports q]

set expected {
  {unconstrained input port} e
  {unconstrained output port} p
  {unconstrained endpoint} {p u/D}
}
set warnings [constraint_warnings]
set failed 0
foreach {kind pins} $expected {
  set named {}
  dict for {msg msg_pins} $warnings {
    if { [string match "*$kind*" $msg] } {
      set named [lsort $msg_pins]
    }
  }
  if { $named != [lsort $pins] } {
    puts "FAIL: $kind warning names {$named}, expected {$pins}"
    set failed 1
  }
}
if { $failed } {
  exit 1
}
puts "PASS"
