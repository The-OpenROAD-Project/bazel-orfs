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
set block [ord::get_db_block]
set um [expr { double([$block getDbUnitsPerMicron]) }]
set files $::env(NETLISTS)
proc in_file { name files } {
  foreach f $files {
    if { [string first "$f/" $name] == 0 || $name eq $f } { return 1 }
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
}
close $out
puts "netlist owners: [llength $files] written to $::env(PROBE_OUT)"
