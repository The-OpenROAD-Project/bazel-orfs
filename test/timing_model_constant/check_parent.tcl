# A parent of blk, timed against its model: the registers on blk's
# constant outputs hold that constant and are not unconstrained
# endpoints; the register on q is timed through the model's arc.
foreach lef [concat $::env(LEFS) [file join [file dirname [info script]] blk.lef]] {
  read_lef $lef
}
foreach lib [concat $::env(LIBS) $::env(MODEL)] {
  read_liberty $lib
}
read_verilog [file join [file dirname [info script]] top.v]
link_design top
create_clock -name clk -period 1000 [get_ports clk]
set_input_delay 0 -clock clk [get_ports d]

set failed 0
proc expect { what got want } {
  if { $got != $want } {
    puts "FAIL: $what: got {$got}, want {$want}"
    set ::failed 1
  }
}
foreach {pin value} {r0/D 0 r1/D 1 rz/D 0} {
  expect "$pin is constant" \
    [sta::pin_sim_logic_value [get_pins $pin]] $value
}
set unconstrained {}
foreach error [sta::check_timing_cmd 0 0 0 0 1 0 0] {
  lappend unconstrained {*}[lrange $error 1 end]
}
expect "unconstrained endpoints" [lsort $unconstrained] {}
expect "paths to rq/D" \
  [expr { [llength [find_timing_paths -to [get_pins rq/D]]] > 0 }] 1
if { $failed } {
  exit 1
}
puts PASS
