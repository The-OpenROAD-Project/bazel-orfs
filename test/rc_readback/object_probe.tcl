proc rss {} {
  set f [open /proc/self/status r]; set d [read $f]; close $f
  regexp {VmRSS:\s+(\d+) kB} $d -> cur
  return [expr { $cur / 1048576.0 }]
}
source $::env(SCRIPTS_DIR)/load.tcl
load_design 6_final.odb 6_final.sdc
puts "DISTINCT baseline rss=[format %.2f [rss]] GB"

# Distinct objects: one dbWire per net, each surfaced to Tcl exactly once.
set before [rss]
set n 0
foreach db_net [[ord::get_db_block] getNets] {
  set w [$db_net getWire]
  incr n
}
set after [rss]
puts [format "DISTINCT getWire over %d distinct nets: rss=%.2f GB delta=%.2f GB per_object=%.1f B" \
  $n $after [expr {$after-$before}] [expr {($after-$before)*1048576.0*1024.0/$n}]]

# Same count of calls, but all on ONE net -- the control.
set one [lindex [[ord::get_db_block] getNets] 0]
set before [rss]
for { set i 0 } { $i < $n } { incr i } { set w [$one getWire] }
set after [rss]
puts [format "DISTINCT getWire %d times on ONE net: delta=%.2f GB per_call=%.1f B" \
  $n [expr {$after-$before}] [expr {($after-$before)*1048576.0*1024.0/$n}]]
puts "DISTINCT done"
