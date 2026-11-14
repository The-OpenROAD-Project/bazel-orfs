# One iteration of an AI loop on module M: M's context database
# (context_db.tcl) loaded with read_db -hier, the new M read and swapped
# in (link_hier_module, replace_hier_module), and the reg2reg slack of
# every endpoint the context times exactly: M's own, and those of the
# capturing registers in M's fanout.
#
#   PSTA_CONTEXT_DB  context_db.tcl's database
#   PSTA_EXACT       context_db.tcl's capturing registers' endpoints
#   PSTA_M           M's instance path
#   PSTA_NEW         the new M's netlists: its module, under a name of its
#                    own, and, unchanged, the modules it instantiates
#   PSTA_NEW_MODULE  that name
#   PSTA_ENDPOINTS   out: "<pin> <slack>" of those endpoints, by pin name
#   PSTA_STATS       out: their worst slack, total negative slack and
#                    violating count, and the load, swap and total seconds
#   plus PSTA_LIBS and PSTA_CLOCKS (common.tcl)

source [file join [file dirname [info script]] common.tcl]

psta_read_libs
read_db -hier $::env(PSTA_CONTEXT_DB)
set loaded [psta_seconds]
foreach v $::env(PSTA_NEW) { read_verilog $v }
link_hier_module $::env(PSTA_NEW_MODULE)
if { ![replace_hier_module $::env(PSTA_M) $::env(PSTA_NEW_MODULE)] } {
  error "iterate.tcl: replace_hier_module $::env(PSTA_M) $::env(PSTA_NEW_MODULE) did nothing"
}
set swapped [psta_seconds]
if { ![psta_clocks] } { error "iterate.tcl: no clock port of PSTA_CLOCKS" }

# the endpoints this context times exactly; the timer escapes [ ] in
# hierarchical names, the lists here do not
set exact [dict create]
set fh [open $::env(PSTA_EXACT)]
foreach l [split [read $fh] "\n"] {
  if { $l ne "" } { dict set exact [string map {\\ ""} $l] 1 }
}
close $fh
set mp "$::env(PSTA_M)/"
set lines {}
set wns ""
set tns 0.0
set violating 0
foreach pin [all_registers -data_pins] {
  set name [string map {\\ ""} [get_full_name $pin]]
  if { ![string equal -length [string length $mp] $mp $name] && ![dict exists $exact $name] } {
    continue
  }
  set s [get_property $pin slack_max]
  if { $s eq "INF" || $s eq "-INF" || $s eq "" } { continue }
  lappend lines "$name $s"
  if { $wns eq "" || $s < $wns } { set wns $s }
  if { $s < 0 } {
    set tns [expr { $tns + $s }]
    incr violating
  }
}
set f [open $::env(PSTA_ENDPOINTS) w]
foreach l [lsort $lines] { puts $f $l }
close $f
set summary [dict create module $::env(PSTA_M) endpoints [llength $lines] \
  wns [expr { $wns eq "" ? 0 : $wns }] tns $tns violating $violating \
  load_seconds $loaded swap_seconds [expr { $swapped - $loaded }] \
  seconds [psta_seconds] peak_mib [psta_peak_mib]]
set f [open $::env(PSTA_STATS) w]
puts $f [psta_json $summary]
close $f
puts "iterate: [psta_json $summary]"
