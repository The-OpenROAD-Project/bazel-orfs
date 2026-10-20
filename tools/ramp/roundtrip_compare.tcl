# Compares two floorplan .odb files on what a macro placement decides:
# every macro's location, orientation and placement status, every
# placement blockage (a macro's halo by its macro), the routing
# obstructions, and the instance and net counts. Run by
# export_roundtrip.py, with openroad:
#
#   COMPARE_A, COMPARE_B  the two .odb files (Bazel's, make's)
#   COMPARE_MOVE          optional: a macro to move one site in B before
#                         comparing, the negative control
#
# Prints each difference and "roundtrip: same" or "roundtrip: N
# differences"; the caller reads the last line.

proc facts { path move } {
  set db [odb::dbDatabase_create]
  odb::read_db $db $path
  set block [[$db getChip] getBlock]
  if { $move ne "" } {
    set inst [$block findInst $move]
    if { $inst == "NULL" } {
      error "roundtrip_compare.tcl: no instance $move to move"
    }
    set loc [$inst getLocation]
    set status [$inst getPlacementStatus]
    $inst setPlacementStatus PLACED
    $inst setLocation [expr { [lindex $loc 0] + [[$inst getMaster] getWidth] }] \
      [lindex $loc 1]
    $inst setPlacementStatus $status
  }
  set out {}
  foreach inst [$block getInsts] {
    if { [$inst isBlock] } {
      lappend out [list macro [$inst getName] [$inst getLocation] \
        [$inst getOrient] [$inst getPlacementStatus]]
    }
  }
  foreach b [$block getBlockages] {
    set i [$b getInstance]
    set r [$b getBBox]
    lappend out [list blockage [expr { $i == "NULL" ? "-" : [$i getName] }] \
      [list [$r xMin] [$r yMin] [$r xMax] [$r yMax]] [$b isSoft] \
      [$b getMaxDensity]]
  }
  lappend out [list obstructions [llength [$block getObstructions]]]
  lappend out [list instances [llength [$block getInsts]]]
  lappend out [list nets [llength [$block getNets]]]
  return [lsort $out]
}

set move [expr { [info exists ::env(COMPARE_MOVE)] ? $::env(COMPARE_MOVE) : "" }]
set a [facts $::env(COMPARE_A) ""]
set b [facts $::env(COMPARE_B) $move]
set n 0
foreach f $a {
  if { [lsearch -exact $b $f] < 0 } {
    puts "roundtrip: only in A: $f"
    incr n
  }
}
foreach f $b {
  if { [lsearch -exact $a $f] < 0 } {
    puts "roundtrip: only in B: $f"
    incr n
  }
}
if { $n == 0 && $a ne $b } {
  puts "roundtrip: the same facts, a different number of times (a doubled blockage?)"
  incr n
}
puts [expr { $n == 0 ? "roundtrip: same" : "roundtrip: $n differences" }]
