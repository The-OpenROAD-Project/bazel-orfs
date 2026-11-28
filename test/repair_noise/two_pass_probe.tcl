# Pass 1 of the two-pass study, read at global route: what global
# placement would have seen with better information, and the file that
# gives it to pass 2.
#
# On one placement, the grt result, timing is read three ways:
#
#   gp  grt parasitics, propagated clock: the truth at grt
#   gi  grt parasitics, ideal clock: the wire is right, the clock is not
#   pi  placement parasitics, ideal clock: what global placement sees
#
# gp against gi is the clock gap, gi against pi the wire gap. Slacks are
# read at every constrained output pin, so each net is keyed by its
# driver. The clock latency of each register clock pin (flops and the
# macros with timing checks) is its propagated arrival minus its clock's
# arrival at the clock's source pin, so edge times and source latency
# cancel. An ideal clock's arrivals cannot stand in for the source: OpenSTA
# keeps the clock network's gate delays in the arrivals it stores at a
# register clock pin either way, and applies the ideal latency only at
# the check.
#
# Writes OUTPUT_LATENCIES (pin, rise max/min, fall max/min, user time
# units) for pass 2's PRE_GLOBAL_PLACE_TCL, and OUTPUT_SLACKS (pin,
# slack gp/gi/pi) for the report.
source $::env(STAGE_SRC_TCL)
set ::env(GUI_TIMING) 1
set ::env(ODB_FILE) $stage_src_staged
source $::env(SCRIPTS_DIR)/open.tcl

# Without routes, read_timing quietly falls back to no parasitics, and
# the "wire gap" would be the gap between placement wires and none.
if { ![grt::have_routes] } {
  error "two_pass_probe: $stage_src_staged has no global routes"
}

set units "[sta::unit_scale_abbreviation time][sta::unit_suffix time]"

proc tp_arrivals { pins } {
  set out {}
  foreach pin $pins {
    set row {}
    foreach p {arrival_max_rise arrival_min_rise arrival_max_fall arrival_min_fall} {
      lappend row [get_property $pin $p]
    }
    lappend out $row
  }
  return $out
}

proc tp_slacks { pins } {
  set out {}
  foreach pin $pins {
    lappend out [get_property $pin slack_max]
  }
  return $out
}

set sinks [all_registers -clock_pins]
set macro_sinks 0
foreach pin $sinks {
  if { [get_property [get_cells -of_objects $pin] is_macro] } { incr macro_sinks }
}
set outs [get_pins -hierarchical * -filter "direction==output"]
puts "TWO_PASS_PROBE sinks=[llength $sinks] macro_sinks=$macro_sinks\
 output_pins=[llength $outs] units=$units"

# gp: as open.tcl left it, with every clock propagated
set_propagated_clock [all_clocks]
set arr_prop [tp_arrivals $sinks]
set s_gp [tp_slacks $outs]

# gi
unset_propagated_clock [all_clocks]
set s_gi [tp_slacks $outs]

# pi
estimate_parasitics -placement
set s_pi [tp_slacks $outs]

# Each clock's arrivals at its source pin, as {rise_max rise_min fall_max fall_min}.
set tp_ref {}
set tp_period {}
foreach clk [all_clocks] {
  set srcs [get_property $clk sources]
  if { ![llength $srcs] } { continue }
  dict set tp_ref [get_name $clk] [lindex [tp_arrivals [list [lindex $srcs 0]]] 0]
  dict set tp_period [get_name $clk] [get_property $clk period]
}

# The network latency of one transition at a sink: the smallest
# non-negative difference to the source's same or opposite transition, so
# a register behind an inverted clock is measured from the edge that
# reaches it. Latency below half a period is assumed.
proc tp_latency { a ref_same ref_opp half } {
  set best ""
  foreach r [list $ref_same $ref_opp] {
    if { ![string is double -strict $r] } { continue }
    set d [expr { $a - $r }]
    if { $d >= -1e-6 && $d < $half && ($best eq "" || $d < $best) } { set best $d }
  }
  return $best
}

set f [open $::env(OUTPUT_LATENCIES) w]
puts $f "# pin\trise_max\trise_min\tfall_max\tfall_min ($units)"
# The latencies pass 1's SDC gives whole clocks: ORFS sets the I/O
# virtual clock's to the tree's insertion delay at CTS. Without them a
# pass that puts the sinks' absolute latencies on the registers would
# time every I/O path against a virtual clock with none.
set sdc_lines 0
set sdc [open [file rootname $stage_src_staged].sdc]
while { [gets $sdc line] >= 0 } {
  if { [regexp {^set_clock_latency .*\[get_clocks } $line] } {
    puts $f "#sdc $line"
    incr sdc_lines
  }
}
close $sdc
set written 0
foreach pin $sinks prop $arr_prop {
  set row {}
  foreach clk [get_property $pin clocks] {
    set name [get_name $clk]
    if { ![dict exists $tp_ref $name] } { continue }
    lassign [dict get $tp_ref $name] rmax rmin fmax fmin
    set half [expr { [dict get $tp_period $name] / 2.0 }]
    lassign $prop armax armin afmax afmin
    set row {}
    foreach a [list $armax $armin $afmax $afmin] same [list $rmax $rmin $fmax $fmin] \
      opp [list $fmax $fmin $rmax $rmin] {
      if { ![string is double -strict $a] } { set row {}; break }
      set l [tp_latency $a $same $opp $half]
      if { $l eq "" } { set row {}; break }
      lappend row [format %.4f $l]
    }
    if { [llength $row] == 4 } { break }
  }
  if { [llength $row] != 4 } { continue }
  puts $f "[get_full_name $pin]\t[join $row \t]"
  incr written
}
close $f
# A clock that never reaches the registers leaves pass 2 nothing to use;
# say so here, not as a pass-2 arm that silently equals the control.
if { $written < 0.9 * [llength $sinks] } {
  error "two_pass_probe: latency for only $written of [llength $sinks] sinks"
}

set f [open $::env(OUTPUT_SLACKS) w]
puts $f "# pin\tgp\tgi\tpi ($units)"
foreach pin $outs a $s_gp b $s_gi c $s_pi {
  puts $f "[get_full_name $pin]\t$a\t$b\t$c"
}
close $f
puts "TWO_PASS_PROBE latencies=$written sdc_clock_latencies=$sdc_lines"
