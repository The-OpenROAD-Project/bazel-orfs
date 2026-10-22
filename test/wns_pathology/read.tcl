# What sets an ORFS design's worst slack at global route (ORFS #4583):
# the facts classify.py turns into pathology flags, one "<key>\t<value>"
# per line in OUT, in the liberty's time unit.
#
# Read the way tools/endpoint_band/read.tcl reads a stage, with the
# one-flop-loop floor of tools/headroom/report_floor_cycles.tcl, whose
# metric call is caught here instead of written to a metrics file.
source $::env(SCRIPTS_DIR)/load.tcl
# the stage is another package's (an ORFS design's own flow): load it
# where it is, through the flow's own load_design
set ::env(RESULTS_DIR) [file dirname $::env(ODB_FILE)]
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing

set wp_out {}
proc wp_put { key value } {
  lappend ::wp_out "$key\t$value"
}

proc wp_name { obj } {
  if { $obj eq "" } { return "" }
  return [get_full_name $obj]
}

# 1 when the pin is on a macro (a LEF block such as a FakeRAM)
proc wp_on_macro { pin } {
  set name [get_full_name $pin]
  set slash [string last / $name]
  if { $slash < 0 } { return 0 }
  set inst [[ord::get_db_block] findInst [string range $name 0 [expr { $slash - 1 }]]]
  if { $inst eq "NULL" } { return 0 }
  return [[$inst getMaster] isBlock]
}

proc wp_is_buffer { pin } {
  set cell [get_cells -quiet -of_objects $pin]
  if { $cell eq "" } { return 0 }
  set lib [get_lib_cells -quiet -of_objects $cell]
  if { $lib eq "" } { return 0 }
  if { [catch { get_property $lib is_buffer } b] } { return 0 }
  return [expr { $b eq "1" }]
}

# A path's facts under a prefix: slack, ends, clocks, macro ends, and for
# a path from an input or to an output, the share of its delay between
# the port and the first (last) cell that is not a buffer: the pin's wire.
proc wp_path { prefix t } {
  wp_put $prefix.slack [get_property $t slack]
  set s [get_property $t startpoint]
  set e [get_property $t endpoint]
  wp_put $prefix.from [wp_name $s]
  wp_put $prefix.to [wp_name $e]
  wp_put $prefix.launch [wp_name [get_property $t startpoint_clock]]
  wp_put $prefix.capture [wp_name [get_property $t endpoint_clock]]
  wp_put $prefix.macro [expr { [wp_on_macro $s] || [wp_on_macro $e] }]
  set pts [get_property $t points]
  set arr {}
  set pins {}
  foreach pt $pts {
    lappend arr [get_property $pt arrival]
    lappend pins [get_property $pt pin]
  }
  set n [llength $arr]
  if { $n < 2 } { return }
  set total [expr { [lindex $arr end] - [lindex $arr 0] }]
  wp_put $prefix.delay $total
  set pin_wire ""
  if { [string first / [get_full_name $s]] < 0 } {
    # from an input port: to the first input pin of a cell that is no buffer
    for { set i 1 } { $i < $n } { incr i } {
      set p [lindex $pins $i]
      if { [get_property $p direction] eq "input" && ![wp_is_buffer $p] } { break }
    }
    if { $i < $n } { set pin_wire [expr { [lindex $arr $i] - [lindex $arr 0] }] }
  } elseif { [string first / [get_full_name $e]] < 0 } {
    # to an output port: from the last output pin of a cell that is no buffer
    for { set i [expr { $n - 2 }] } { $i >= 0 } { incr i -1 } {
      set p [lindex $pins $i]
      if { [get_property $p direction] eq "output" && ![wp_is_buffer $p] } { break }
    }
    if { $i >= 0 } { set pin_wire [expr { [lindex $arr end] - [lindex $arr $i] }] }
  }
  if { $pin_wire ne "" } { wp_put $prefix.pin_wire $pin_wire }
}

set groups [dict create \
  reg2reg [list -from [all_registers -clock_pins] -to [all_registers -data_pins]] \
  in2reg [list -from [all_inputs -no_clocks] -to [all_registers -data_pins]] \
  reg2out [list -from [all_registers -clock_pins] -to [all_outputs]] \
  in2out [list -from [all_inputs -no_clocks] -to [all_outputs]]]

foreach c [all_clocks] {
  wp_put clock.[get_full_name $c] [get_property $c period]
  # a virtual clock, such as the one ORFS's SDCs time IO against, has no
  # source pin: a path to or from it does not cross into another domain
  if { [llength [get_property $c sources]] == 0 } {
    wp_put virtual.[get_full_name $c] 1
  }
}
dict for { g sel } $groups {
  set ps [find_timing_paths {*}$sel -sort_by_slack -group_path_count 1]
  if { [llength $ps] } { wp_path $g [lindex $ps 0] }
}
set worst [lindex [find_timing_paths -sort_by_slack -group_path_count 1] 0]
if { $worst ne "" } { wp_path worst $worst }
wp_put wns [sta::worst_slack -max]

# the ten worst reg2reg endpoints, worst first, as periods
set ends {}
foreach t [find_timing_paths {*}[dict get $groups reg2reg] -sort_by_slack \
             -endpoint_path_count 1 -group_path_count 10 -unique_paths_to_endpoint] {
  set clk [get_property $t endpoint_clock]
  if { $clk eq "" } { continue }
  lappend ends [expr { [get_property $clk period] - [get_property $t slack] }]
}
wp_put reg2reg.top10 [join $ends " "]

# check_setup, every warning a bare check_setup gives, by count
# (.claude/skills/check-setup); none is a clean check, not a missing one
wp_put check_setup.ran 1
foreach error [sta::check_timing_cmd 1 1 1 1 1 1 1] {
  set msg [lindex $error 0]
  set count 0
  foreach obj [lrange $error 1 end] {
    if { [string match "|*" $obj] || [string match "---*" $obj] } { continue }
    incr count
  }
  regexp {There (?:is|are) (\d+) } $msg -> count
  regsub {There (?:is|are) \d+ } $msg {} key
  wp_put check_setup.[string map {" " _ . ""} [string trim $key]] $count
}

# repair_timing -hold names the buffers it inserts hold<n>; of a sample,
# how many have an input port among the startpoints of their fan-in
set insts 0
set holds {}
foreach inst [[ord::get_db_block] getInsts] {
  if { [[$inst getMaster] isCore] } { incr insts }
  if { [string match "hold*" [$inst getName]] } { lappend holds [$inst getName] }
}
wp_put instances $insts
wp_put hold.buffers [llength $holds]
set sample [lrange $holds 0 199]
set from_input 0
foreach h $sample {
  set in [get_pins -quiet -of_objects [get_cells $h] -filter "direction == input"]
  if { $in eq "" } { continue }
  foreach s [get_fanin -to $in -startpoints_only -flat] {
    if { [string first / [get_full_name $s]] < 0 } { incr from_input; break }
  }
}
wp_put hold.sampled [llength $sample]
wp_put hold.from_input $from_input

# the one-flop-loop floor; its metric call is where the value is caught
rename utl::metric_float wp_metric_float
proc utl::metric_float { name value } {
  if { $name eq "timing__floor_cycles" } { wp_put floor $value }
}
source $::env(FLOOR_TCL)
rename utl::metric_float ""
rename wp_metric_float utl::metric_float

set f [open $::env(OUT) w]
puts $f [join $wp_out "\n"]
close $f
