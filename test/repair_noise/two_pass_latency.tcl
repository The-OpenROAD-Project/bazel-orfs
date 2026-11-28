# PRE_GLOBAL_PLACE_TCL for pass 2: the clock latency pass 1's grt
# measured at each register clock pin, as ideal-clock network latency,
# so timing-driven global placement sees pass 1's skew instead of none.
# OpenSTA honours per-pin network latency on an ideal clock (gpl's own
# -virtual_cts sets it the same way). The SDC is read from file by each
# stage, so the latencies live only in this global placement.
set tp_f [open $::env(TWO_PASS_LATENCIES)]
set tp_set 0
set tp_missing 0
set tp_sdc 0
while { [gets $tp_f tp_line] >= 0 } {
  # pass 1's whole-clock latencies, the I/O virtual clock's among them
  if { [string range $tp_line 0 4] eq "#sdc " } {
    eval [string range $tp_line 5 end]
    incr tp_sdc
    continue
  }
  if { [string index $tp_line 0] eq "#" } { continue }
  lassign [split $tp_line "\t"] tp_name rmax rmin fmax fmin
  set tp_pin [sta::find_pin $tp_name]
  if { $tp_pin eq "NULL" || $tp_pin eq "" } {
    incr tp_missing
    continue
  }
  set_clock_latency -rise -max $rmax $tp_pin
  set_clock_latency -rise -min $rmin $tp_pin
  set_clock_latency -fall -max $fmax $tp_pin
  set_clock_latency -fall -min $fmin $tp_pin
  incr tp_set
}
close $tp_f
puts "TWO_PASS_LATENCY set=$tp_set missing=$tp_missing sdc=$tp_sdc"
# Pass 2 starts from pass 1's floorplan, so every register is there; a
# miss means the names do not line up and the arm would measure nothing.
if { $tp_missing > 0.01 * ($tp_set + $tp_missing) } {
  error "two_pass_latency: $tp_missing of [expr { $tp_set + $tp_missing }] pins not found"
}
