set placed [expr {[llength [lsearch -all -inline -not [lmap i [[ord::get_db_block] getInsts] {$i getPlacementStatus}] NONE]] > 0}]
set stage [file rootname [file tail [ord::get_db_block]]]
if {[catch {estimate_parasitics -global_routing} e]} {puts "GRT RC failed: $e"; estimate_parasitics -placement}
set p [get_property [lindex [all_clocks] 0] period]
set w [sta::worst_slack -max]
set paths [find_timing_paths -path_delay max -group_path_count 100000 -endpoint_path_count 1 -sort_by_slack]
set h [dict create]; set n 0; set tns 0
set groups [dict create]
foreach t $paths {
  set s [get_property $t slack]; set ep [get_full_name [get_property $t endpoint]]
  if {[regexp {_ff/D$|rf\.rf\[|rf\[} $ep]} {set k rf} elseif {[regexp {/D$} $ep]} {set k reg} else {set k out}
  if {$s < 0} {set tns [expr $tns+$s]; dict incr groups $k}
  set b [expr {int(floor($s/25.0))*25}]
  if {$b > 200} {set b 200}
  dict incr h "$b $k"
  incr n
}
set o [format "period %.0f  WNS %.1f  minperiod %.0f  TNS %.0f  endpoints %d  failing %s\n" $p $w [expr $p-$w] $tns $n $groups]
foreach b [lsort -integer -unique [lmap k [dict keys $h] {lindex $k 0}]] {
  set r [expr {[dict exists $h "$b rf"] ? [dict get $h "$b rf"] : 0}]
  set g [expr {[dict exists $h "$b reg"] ? [dict get $h "$b reg"] : 0}]
  set u [expr {[dict exists $h "$b out"] ? [dict get $h "$b out"] : 0}]
  append o [format "%6d..%-5s rf %5d  otherreg %5d  out %4d  %s\n" $b [expr {$b==200?"":$b+25}] $r $g $u [string repeat "#" [expr {($r+$g+$u+19)/20}]]]
}
set o
