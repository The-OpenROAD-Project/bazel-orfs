# The crossing ledger's reference, on the flat top level at global route:
# for every crossing net, the register-to-register paths through it as
# the top level times them, each with its clock taken out, which is what
# the ledger's halves (crossing_ledger.tcl) sum to without a top level.
# A test's reference, for a design small enough for a path search per
# net (crossing_ledger_check.py); the ledger itself searches none.
#
# A crossing net: a signal net driven in one macro and read in another
# (an instance name's first level, the instance it was dissolved from).
# Its name is the parent's port, u_<block>__<pin>, the ledger's name for
# it.
#
# CROSSING_TXT, ps:
#
#   path <net> <need> <free> <clock> <startpoint> <endpoint>
#   none <net>
#
# need: the period less the path's slack. free: the path from its
# launching register's clock pin on, the setup included. clock: need
# less free, the launch clock's latency less the capture clock's and
# less the common path's pessimism. none: no register-to-register path
# goes through the net.
#
#   LEDGER_TOP_PATHS   the paths kept per net, the worst by slack (64),
#                      four to an endpoint: the path that needs the most
#                      with its clock taken out is not always the worst
#                      by slack
# top_level.tcl sources this with its routed design loaded and estimated
if { ![info exists ::crossing_paths_loaded] } {
  source $::env(SCRIPTS_DIR)/load.tcl
  load_design 5_1_grt.odb 5_1_grt.sdc
  set_propagated_clock [all_clocks]
  estimate_parasitics -global_routing
}

set per_net [expr {
  [env_var_exists_and_non_empty LEDGER_TOP_PATHS] ? $::env(LEDGER_TOP_PATHS) : 64
}]
set clock [lindex [all_clocks] 0]

proc top_ps { seconds } {
  return [expr { $seconds * 1e12 }]
}

# an instance name's first level, at the first divider not escaped; none
# for an instance of the top level's own (its clock tree)
proc macro_of_inst { name } {
  set slash [string first / $name]
  while { $slash > 0 && [string index $name [expr { $slash - 1 }]] eq "\\" } {
    set slash [string first / $name [expr { $slash + 1 }]]
  }
  if { $slash < 0 } { return "" }
  return [string range $name 0 [expr { $slash - 1 }]]
}

# Every register's clock pin arrivals, by its instance, before any path
# is searched: reading a pin's arrival frees the paths a search returned.
set clock_pins [dict create]
foreach pin [all_registers -clock_pins] {
  set name [get_full_name $pin]
  set inst [string range $name 0 [expr { [string last / $name] - 1 }]]
  foreach rf {rise fall} {
    set t [get_property $pin arrival_max_$rf]
    if { [string is double -strict $t] && abs($t) < 1e15 } {
      dict lappend clock_pins $inst [top_ps [sta::time_ui_sta $t]]
    }
  }
}

set crossings {}
foreach net [[ord::get_db_block] getNets] {
  if { [$net getSigType] ne "SIGNAL" } { continue }
  set from ""
  set loads {}
  foreach iterm [$net getITerms] {
    set inst [[$iterm getInst] getName]
    if { [$iterm isOutputSignal] } {
      set from [macro_of_inst $inst]
    } elseif { [$iterm isInputSignal] } {
      lappend loads [list [macro_of_inst $inst] $inst/[[$iterm getMTerm] getName]]
    }
  }
  if { $from eq "" } { continue }
  set over {}
  foreach load $loads {
    lassign $load to pin
    if { $to ne "" && $to ne $from } { lappend over $pin }
  }
  if { [llength $over] } {
    lappend crossings [list [$net getName] $over]
  }
}

set period [top_ps [$clock period]]
set rows {}
set none {}
foreach crossing [lsort -index 0 $crossings] {
  lassign $crossing net over
  set found 0
  foreach end [find_timing_paths -through [get_pins $over] -path_delay max \
    -group_path_count $per_net -endpoint_path_count 4 -unique_paths_to_endpoint] {
    set start [get_property $end startpoint]
    set to [get_property $end endpoint]
    # register to register: a port has no instance
    if { [$start is_top_level_port] || [$to is_top_level_port] } {
      continue
    }
    set name [get_full_name $start]
    set inst [string range $name 0 [expr { [string last / $name] - 1 }]]
    if { ![dict exists $clock_pins $inst] } {
      utl::error FLW 52 "crossing_ledger_top: $net: a path starts at $name, which no\
        clock arrives at"
    }
    # the clock edge that launched it: the last to arrive at the
    # register's clock pin before its output moved
    set moved [top_ps [[[$end path] start_path] arrival]]
    set launch ""
    foreach t [dict get $clock_pins $inst] {
      if { $t <= $moved && ($launch eq "" || $t > $launch) } { set launch $t }
    }
    if { $launch eq "" } {
      utl::error FLW 52 "crossing_ledger_top: $net: a path starts at $name, which no\
        clock arrives at"
    }
    set need [expr { $period - [top_ps [sta::time_ui_sta [get_property $end slack]]] }]
    set free [expr { [top_ps [$end data_arrival_time]] - $launch + [top_ps [$end margin]] }]
    lappend rows [list $net $need $free [expr { $need - $free }] $name [get_full_name $to]]
    incr found
  }
  if { !$found } { lappend none $net }
}

set f [open $::env(CROSSING_TXT) w]
puts $f "# reg2reg paths through each crossing net at global route, ps; period\
  [format %.2f $period], the $per_net worst by slack per net"
puts $f "# path <net> <need> <free> <clock> <startpoint> <endpoint>; none <net>"
foreach row $rows {
  lassign $row net need free clk start to
  puts $f [format "path %s %.2f %.2f %.2f %s %s" $net $need $free $clk $start $to]
}
foreach net $none {
  puts $f "none $net"
}
close $f
puts "crossing_ledger_top: [llength $crossings] crossing nets, [llength $none] with no\
  reg2reg path, [llength $rows] paths"
