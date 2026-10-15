# Netlist owners: where each planned register file's owner put its own
# cells. Run in an odb-debug session (GUI_TIMING=0) on a placed parent, a
# place-stage checkpoint of the plan as it is. The owner of a netlist is
# the module that instantiates it, the instance's parent in the flat
# names (the whole parent for a netlist at the top); its cells are the
# parent cells under that prefix less the cells of every planned netlist
# and the hardened blocks. NETLISTS is the plan's netlist instances,
# space separated. One line per netlist to PROBE_OUT:
#
#   owner <instance> <x_um> <y_um> <cells>
#
# x and y are the median of the owner's cell origins: the plan's owner_um
# for that netlist, which the planner centres the file on. A file placed
# away from its owner's logic stretches that logic's decode and select
# cells across the gap; global placement does not pull a FIRM file in.
# How far it stretched is a second line per netlist:
#
#   scatter <instance> <core x0 y0 x1 y1 um> <periphery cells> <p50 um> <p90 um> <beyond 500 um>
#
# the core is the box of the netlist's FIRM cells, the periphery its other
# cells (the decode and select the generator leaves to the parent), each
# at its Manhattan distance outside the core's box: the percentiles and
# how many lie more than 500 um out (ideas/xiangshan-timing.md, entry 53).
set block [ord::get_db_block]
set um [expr { double([$block getDbUnitsPerMicron]) }]
set files $::env(NETLISTS)
# a netlist's own cells: under its instance at either separator
proc of_file { name f } {
  return [expr { [string first "$f/" $name] == 0 || [string first "$f." $name] == 0
    || $name eq $f }]
}
proc in_file { name files } {
  foreach f $files {
    if { [of_file $name $f] } { return 1 }
  }
  return 0
}
set out [open $::env(PROBE_OUT) w]
foreach f $files {
  # the owner is the instance's path up to its last separator, "/" in a
  # hierarchical netlist's names and "." in a flattened one; a netlist at
  # the top is owned by the whole parent
  set owner ""
  set prefix ""
  if { [regexp {^(.*[./])[^./]+$} $f -> prefix] } {
    set owner [string range $prefix 0 end-1]
  }
  set xs {}
  set ys {}
  foreach inst [$block getInsts] {
    set name [$inst getName]
    if { $prefix ne "" && [string first $prefix $name] != 0 } { continue }
    if { [[$inst getMaster] isBlock] || [in_file $name $files] } { continue }
    set loc [$inst getLocation]
    lappend xs [lindex $loc 0]
    lappend ys [lindex $loc 1]
  }
  set n [llength $xs]
  if { $n == 0 } {
    utl::error FLW 3 "netlist owners: no placed cells under $owner"
  }
  set x [lindex [lsort -integer $xs] [expr { $n / 2 }]]
  set y [lindex [lsort -integer $ys] [expr { $n / 2 }]]
  puts $out [format "owner %s %.1f %.1f %d" $f [expr { $x / $um }] [expr { $y / $um }] $n]
  set x0 1e18
  set y0 1e18
  set x1 -1e18
  set y1 -1e18
  set loose {}
  foreach inst [$block getInsts] {
    if { ![of_file [$inst getName] $f] } { continue }
    if { [$inst getPlacementStatus] eq "FIRM" } {
      set b [$inst getBBox]
      set x0 [expr { min($x0, [$b xMin]) }]
      set y0 [expr { min($y0, [$b yMin]) }]
      set x1 [expr { max($x1, [$b xMax]) }]
      set y1 [expr { max($y1, [$b yMax]) }]
    } else {
      lappend loose $inst
    }
  }
  if { $x1 < $x0 } {
    utl::error FLW 4 "netlist owners: $f has no FIRM core"
  }
  set ds {}
  foreach inst $loose {
    lassign [$inst getLocation] x y
    set dx [expr { $x < $x0 ? $x0 - $x : ($x > $x1 ? $x - $x1 : 0) }]
    set dy [expr { $y < $y0 ? $y0 - $y : ($y > $y1 ? $y - $y1 : 0) }]
    lappend ds [expr { ($dx + $dy) / $um }]
  }
  set ds [lsort -real $ds]
  set k [llength $ds]
  set far 0
  foreach d $ds {
    if { $d > 500 } { incr far }
  }
  puts $out [format "scatter %s %.1f %.1f %.1f %.1f %d %.1f %.1f %d" $f \
    [expr { $x0 / $um }] [expr { $y0 / $um }] [expr { $x1 / $um }] [expr { $y1 / $um }] \
    $k [lindex $ds [expr { $k / 2 }]] [lindex $ds [expr { $k * 9 / 10 }]] $far]
}
close $out
puts "netlist owners: [llength $files] written to $::env(PROBE_OUT)"
