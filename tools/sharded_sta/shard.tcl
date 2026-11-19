# One shard of a sharded timing: its modules' partitions and their
# ancestors' as netlists, every other subtree as its root's timing model,
# timed with the ideal clock of PSTA_CLOCKS. Writes a row per register
# data pin of the modules the shard owns: "<pin> <slack> <exact>", exact 1
# when no timing model reaches the pin, through its outputs or through the
# nets its inputs load, so every path into it is timed as in the netlist.
#
#   PSTA_NETLIST  partition netlists
#   PSTA_MODELS   timing models (liberty), one cell per modelled module
#   PSTA_MODEL_CELLS  the modelled modules, the models' cell names
#   PSTA_TOP      the design's top module
#   PSTA_LISTED   the kept modules this shard lists
#   PSTA_LISTED_ELSEWHERE  those the other shards list
#   PSTA_GLUE     1 for the glue shard, which owns what no shard lists
#   PSTA_ROWS     out: the rows, sorted by pin
#   PSTA_PATHS    out: report_checks of the PSTA_PATH_COUNT worst owned
#                 endpoints
#   PSTA_STATS    out: cells, endpoints, wall seconds, peak memory, JSON
#   PSTA_THREADS  the threads the timer uses
#   plus PSTA_LIBS and PSTA_CLOCKS (module_sta's common.tcl)

source [file join [file dirname [info script]] .. module_sta common.tcl]

set link_make_black_boxes 0
sta::set_thread_count $::env(PSTA_THREADS)
psta_read_libs
set models $::env(PSTA_MODELS)
foreach lib $models { read_liberty $lib }
set t_libs [psta_seconds]
foreach netlist $::env(PSTA_NETLIST) { read_verilog $netlist }
link_design $::env(PSTA_TOP)
set t_link [psta_seconds]
if { ![psta_clocks] && [llength [all_registers]] } {
  error "shard.tcl: no clock port of PSTA_CLOCKS on $::env(PSTA_TOP)"
}

# the instances this shard owns: one whose module it lists, or whose
# module no shard lists and whose parent it owns; the top's owner is the
# glue shard
set listed [dict create]
foreach m $::env(PSTA_LISTED) { dict set listed $m 1 }
foreach m $::env(PSTA_LISTED_ELSEWHERE) { dict set listed $m 0 }
set top_owned $::env(PSTA_GLUE)
set hier {}
foreach c [get_cells -hierarchical -quiet -filter "is_hierarchical == 1" *] {
  set name [get_full_name $c]
  lappend hier [list [llength [split $name /]] $name [get_property $c ref_name]]
}
set inst_owned [dict create]
foreach h [lsort -integer -index 0 $hier] {
  lassign $h depth name ref
  if { [dict exists $listed $ref] } {
    dict set inst_owned $name [dict get $listed $ref]
    continue
  }
  set i [string last / $name]
  set parent [string range $name 0 [expr { $i - 1 }]]
  if { $i < 0 } {
    dict set inst_owned $name $top_owned
  } else {
    dict set inst_owned $name [dict get $inst_owned $parent]
  }
}

# the timing models' cells, and every endpoint a model reaches: through
# its outputs, and through the nets its inputs load, whose drivers' delays
# and slews follow the model's pin capacitance, not the netlist's loads
set modelled [dict create]
set sources {}
foreach cell $::env(PSTA_MODEL_CELLS) {
  foreach inst [get_cells -hierarchical -quiet -filter "ref_name == $cell" *] {
    dict set modelled [get_full_name $inst] 1
    foreach p [get_pins -quiet -of_objects $inst] {
      if { [get_property $p direction] eq "output" } {
        lappend sources $p
        continue
      }
      set net [get_nets -quiet -of_objects $p]
      if { $net eq "" } { continue }
      foreach d [get_pins -quiet -of_objects $net -filter "direction == output"] {
        if { ![dict exists $modelled [get_full_name [get_cells -of_objects $d]]] } { lappend sources $d }
      }
    }
  }
}
set tainted [dict create]
if { [llength $sources] } {
  foreach p [get_fanout -from $sources -flat -endpoints_only -trace_arcs all] {
    dict set tainted [get_full_name $p] 1
  }
}

proc owner_of { pin } {
  set path [get_full_name $pin]
  set i [string last / $path]
  set path [string range $path 0 [expr { $i - 1 }]]
  while { 1 } {
    set i [string last / $path]
    if { $i < 0 } { return $::top_owned }
    set path [string range $path 0 [expr { $i - 1 }]]
    if { [dict exists $::inst_owned $path] } { return [dict get $::inst_owned $path] }
  }
}

set owned_pins {}
set slacks [dict create]
foreach pin [all_registers -data_pins] {
  # a timing model's setup checks are its own registers', reported by the
  # shard that holds its netlist
  if { [dict exists $modelled [get_full_name [get_cells -of_objects $pin]]] } { continue }
  if { ![owner_of $pin] } { continue }
  set s [get_property $pin slack_max]
  if { $s eq "INF" || $s eq "-INF" || $s eq "" } { continue }
  lappend owned_pins $pin
  dict set slacks [get_full_name $pin] $s
}

set worst {}
dict for {name s} $slacks { lappend worst [list $s $name] }
set f [open $::env(PSTA_PATHS) w]
close $f
foreach w [lrange [lsort -real -index 0 $worst] 0 [expr { $::env(PSTA_PATH_COUNT) - 1 }]] {
  sta::redirect_file_append_begin $::env(PSTA_PATHS)
  puts "endpoint [lindex $w 1]"
  report_checks -path_delay max -to [get_pins [lindex $w 1]] -digits 1
  sta::redirect_file_end
}

set rows {}
set nexact 0
foreach pin $owned_pins {
  set name [get_full_name $pin]
  set exact [expr { ![dict exists $tainted $name] }]
  incr nexact $exact
  lappend rows "$name [dict get $slacks $name] $exact"
}
set rows [lsort $rows]
set f [open $::env(PSTA_ROWS) w]
if { [llength $rows] } { puts $f [join $rows "\n"] }
close $f

set f [open $::env(PSTA_STATS) w]
puts $f [psta_json [dict create top $::env(PSTA_TOP) \
  cells [llength [get_cells -hierarchical -quiet -filter "is_hierarchical == 0" *]] \
  models [llength $models] modelled_instances [dict size $modelled] \
  endpoints [llength $rows] exact $nexact \
  libs_seconds $t_libs link_seconds [expr { $t_link - $t_libs }] \
  seconds [psta_seconds] peak_mib [psta_peak_mib]]]
close $f
