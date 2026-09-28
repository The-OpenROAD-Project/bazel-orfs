# What ADDITIONAL_ODB_FILES promises, read off a dissolved and placed parent: the
# netlist for the parent-level co-simulation, and a report of facts the
# test asserts (dissolve_check_test.py).
source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $::env(ODB_FILE)]
load_design $odb_tail [file rootname $odb_tail].sdc
set block [ord::get_db_block]
write_verilog $::env(OUTPUT_V)
set f [open $::env(OUTPUT_TXT) w]
set macros 0
set cells 0
set not_firm 0
set touchable 0
set off_row 0
set rows {}
foreach r [$block getRows] {
  lappend rows [list [lindex [$r getOrigin] 1] [$r getOrient]]
}
foreach i [$block getInsts] {
  if {[[$i getMaster] getName] eq "MainBtbWriteBufferEnq"} { incr macros }
  if {![string match "u_enq.*" [$i getName]]} { continue }
  incr cells
  if {[$i getPlacementStatus] ne "FIRM"} { incr not_firm }
  # Interior combinational cells are dont_touch; flops and cells on a
  # net that leaves the block are not (dissolve_odb.tcl).
  set interior 1
  foreach it [$i getITerms] {
    set n [$it getNet]
    if {$n == "NULL" || [$n getSigType] in {POWER GROUND}} { continue }
    foreach o [$n getITerms] {
      if {![string match "u_enq.*" [[$o getInst] getName]]} { set interior 0 }
    }
    if {[llength [$n getBTerms]] > 0} { set interior 0 }
  }
  if {$interior && ![[$i getMaster] isSequential] && ![$i isDoNotTouch]} { incr touchable }
  set y [lindex [$i getLocation] 1]
  set ok 0
  foreach r $rows {
    set up [expr {[lindex $r 1] in {R0 MY}}]
    if {[lindex $r 0] == $y && $up == ([$i getOrient] in {R0 MY})} { set ok 1; break }
  }
  if {!$ok} { incr off_row }
}
puts $f "macros $macros"
puts $f "cells $cells"
puts $f "not_firm $not_firm"
puts $f "touchable $touchable"
puts $f "off_row $off_row"
set legal [catch {check_placement -verbose} msg]
puts $f "check_placement [expr {$legal ? {fail} : {ok}}]"
close $f
