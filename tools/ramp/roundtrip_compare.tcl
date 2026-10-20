# Compares two floorplan .odb files on what a macro placement decides:
# every macro's location, orientation and placement status, every
# placement blockage (a macro's halo by its macro), the routing
# obstructions, the instance and net counts, and a checksum of every
# instance's place. Run by
# export_roundtrip.py, with openroad:
#
#   COMPARE_A, COMPARE_B  the two .odb files (Bazel's, make's)
#   COMPARE_MOVE          optional: a macro to move one site in B before
#                         comparing, the negative control
#   COMPARE_SEEDS         optional, 0: the checksum leaves out standard
#                         cells not fixed (PLACED or NONE): the seeds
#                         rtl_macro_placer leaves at its cluster centres,
#                         which a macro placement snapshot does not run;
#                         their counts are printed, not compared
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
  # every instance's place, as one checksum: a cell moved is a difference
  set seeds [expr { [info exists ::env(COMPARE_SEEDS)] && !$::env(COMPARE_SEEDS) }]
  set cells {}
  set seeded {PLACED 0 NONE 0}
  foreach inst [$block getInsts] {
    set status [$inst getPlacementStatus]
    if { $seeds && ![$inst isBlock] && $status in {PLACED NONE} } {
      dict incr seeded $status
      continue
    }
    lappend cells [list [$inst getName] [$inst getLocation] [$inst getOrient] \
      [$inst getPlacementStatus]]
  }
  if { $seeds } {
    puts "roundtrip: note: standard cells not fixed in $::side, not compared:\
      [dict get $seeded PLACED] PLACED, [dict get $seeded NONE] NONE"
  }
  lappend out [list placement [zlib crc32 [join [lsort $cells] "\n"]]]
  lappend out [list obstructions [llength [$block getObstructions]]]
  lappend out [list instances [llength [$block getInsts]]]
  lappend out [list nets [llength [$block getNets]]]
  return [lsort $out]
}

set move [expr { [info exists ::env(COMPARE_MOVE)] ? $::env(COMPARE_MOVE) : "" }]
set ::side A
set a [facts $::env(COMPARE_A) ""]
set ::side B
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
