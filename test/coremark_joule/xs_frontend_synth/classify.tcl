# openroad -exit classify.tcl, with load.tcl's environment and XS_OUT.
# Classify the reg2reg endpoints over 1,000 ps: through a macro or not, by
# endpoint module, and the split of the worst path that avoids macros.
source [file dirname [info script]]/load.tcl
proc mod2 {n} { set p [split $n /]; if {[llength $p] > 2} { return [join [lrange $p 0 1] /] } ; return [lindex $p 0] }
set clk_ps [get_property [sta::find_clock clk] period]
set pes [find_timing_paths -path_group reg2reg -path_delay max -group_path_count 1000000 -endpoint_path_count 1 -slack_max [expr {$clk_ps - 1000}] -unique_paths_to_endpoint]
set f [open $::env(XS_OUT) w]
set thru [dict create]; set ep [dict create]; set nomac {}
set hist [dict create]; set worst_nores 0.0; set worst_nomac 0.0
foreach pe $pes {
  set macro none
  foreach pin [[$pe path] pins] {
    set r [get_property [$pin instance] ref_name]
    if {[string match Ftq* $r] || [string match array_* $r]} { set macro $r; break }
  }
  dict incr thru $macro
  set per [expr {$clk_ps - [$pe slack] * 1e12}]
  dict incr hist [expr {int($per / 100) * 100}]
  if {$macro ne "FtqMetaQueueResolve" && $per > $worst_nores} { set worst_nores $per }
  if {$macro eq "none" && $per > $worst_nomac} { set worst_nomac $per }
  set e [mod2 [get_full_name [$pe pin]]]
  dict incr ep "$e ([expr {$macro eq {none} ? {no macro} : {macro}}])"
  if {$macro eq "none" && [llength $nomac] == 0} { set nomac [$pe pin] }
}
puts $f "endpoints over 1000 ps: [llength $pes]"
puts $f "-- through"; dict for {k v} $thru { puts $f "  $k $v" }
puts $f "-- period histogram (ps, endpoints)"; foreach k [lsort -integer [dict keys $hist]] { puts $f "  $k-[expr {$k+99}] [dict get $hist $k]" }
puts $f "worst period not through FtqMetaQueueResolve: [format %.0f $worst_nores] ps"
puts $f "worst period through no macro: [format %.0f $worst_nomac] ps"
set l {}; dict for {k v} $ep { lappend l [list $v $k] }
puts $f "-- endpoint module"; foreach x [lrange [lsort -integer -decreasing -index 0 $l] 0 14] { puts $f "  [lindex $x 0] [lindex $x 1]" }
close $f
if {$nomac ne ""} {
  report_checks -path_group reg2reg -path_delay max -to $nomac -fields {slew cap fanout} -digits 1 > [file rootname $::env(XS_OUT)]_nomacro.txt
}
