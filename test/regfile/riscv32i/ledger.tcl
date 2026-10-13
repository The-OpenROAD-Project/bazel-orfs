# ledger.tcl: where the core goes, on any stage's ODB. Every um2 of the
# core is in exactly one line: macros by master (box, halo ring), core
# not covered by rows (cut around macros, margins), standard cells,
# taps/endcaps, fill, and empty row area. The register file's cells
# (riscv.dp/rf/*, or riscv.dp.rf/* where synthesis flattened a
# periphery wrapper) are split out of the standard cells, and their
# bounding box and fill are reported once dissolved.
set b [ord::get_db_block]; set u [expr double([$b getDbUnitsPerMicron])]
proc um2 {a} { return [expr {$a/$::u/$::u}] }
proc boxa {bb} { return [expr {double([$bb xMax]-[$bb xMin])*([$bb yMax]-[$bb yMin])}] }
set c [$b getCoreArea]; set core [boxa $c]
set rows 0; foreach r [$b getRows] { set rows [expr {$rows+[boxa [$r getBBox]]}] }
set macros [dict create]; set std 0; set rf 0; set nrf 0; set tap 0; set fill 0; set unplaced 0
set rx0 1e18; set ry0 1e18; set rx1 -1e18; set ry1 -1e18; set rfbox 0
foreach i [$b getInsts] {
  set m [$i getMaster]; set a [expr {double([$m getWidth])*[$m getHeight]}]
  if {[$m isBlock]} {
    set bb [$i getBBox]; set h [$i getHalo]; set ring 0
    if {$h ne "NULL"} {
      set ring [expr {double([$bb xMax]-[$bb xMin]+[$h xMin]+[$h xMax])*([$bb yMax]-[$bb yMin]+[$h yMin]+[$h yMax])-$a}]
    }
    set k [$m getName]
    if {![dict exists $macros $k]} { dict set macros $k [list 0 0 0 [$m getWidth] [$m getHeight]] }
    lassign [dict get $macros $k] n sa sr w hh
    dict set macros $k [list [incr n] [expr {$sa+$a}] [expr {$sr+$ring}] $w $hh]
    continue
  }
  set t [$m getType]
  if {[string match *WELLTAP $t] || [string match ENDCAP* $t] || [string match TAP* [$i getName]] || [string match PHY_* [$i getName]]} { set tap [expr {$tap+$a}]; continue }
  if {[string match *FILL* [$m getName]] || [string match *DECAP* [$m getName]]} { set fill [expr {$fill+$a}]; continue }
  if {![$i isPlaced]} { set unplaced [expr {$unplaced+$a}] }
  if {[string match {riscv.dp[./]rf[./]*} [$i getName]]} {
    set rf [expr {$rf+$a}]; incr nrf
    if {[$i getPlacementStatus] eq "FIRM"} {
      set bb [$i getBBox]; set rfbox [expr {$rfbox+$a}]
      set rx0 [expr {min($rx0,[$bb xMin])}]; set ry0 [expr {min($ry0,[$bb yMin])}]
      set rx1 [expr {max($rx1,[$bb xMax])}]; set ry1 [expr {max($ry1,[$bb yMax])}]
    }
    continue
  }
  set std [expr {$std+$a}]
}
set mac 0; set ring 0
set o [format "core %.0f um2 (%.1f x %.1f um), rows %.0f um2, core without rows %.0f um2\n" [um2 $core] [expr {[$c dx]/$u}] [expr {[$c dy]/$u}] [um2 $rows] [um2 [expr {$core-$rows}]]]
dict for {k v} $macros {
  lassign $v n sa sr w hh
  set mac [expr {$mac+$sa}]; set ring [expr {$ring+$sr}]
  append o [format "  macro %-22s x%d  %.2f x %.2f um, %.0f um2, halo ring %.0f um2\n" $k $n [expr {$w/$u}] [expr {$hh/$u}] [um2 $sa] [um2 $sr]]
}
append o [format "  rows lost beyond the macro boxes (cut halos, margins): %.0f um2\n" [um2 [expr {$core-$rows-$mac}]]]
set pb 0; foreach bl [$b getBlockages] { set pb [expr {$pb+[boxa [$bl getBBox]]}] }
append o [format "  placement blockages %.0f um2\n" [um2 $pb]]
append o [format "standard cells %.0f um2 (+ register file %d cells %.0f um2), taps/endcaps %.0f, fill %.0f, unplaced %.0f\n" [um2 $std] $nrf [um2 $rf] [um2 $tap] [um2 $fill] [um2 $unplaced]]
append o [format "empty row area %.0f um2 (rows %.0f%% full)\n" [um2 [expr {$rows-$std-$rf-$tap-$fill}]] [expr {100*($std+$rf+$tap+$fill)/$rows}]]
append o [format "instance area / core = %.1f%% (utilization as initialize_floorplan counts it: macro boxes + cells)\n" [expr {100*($mac+$std+$rf)/$core}]]
if {$rfbox > 0} {
  set bx [expr {double($rx1-$rx0)*($ry1-$ry0)}]
  append o [format "register file FIRM box %.1f x %.1f um = %.0f um2, its cells %.0f um2 (%.0f%%)\n" [expr {($rx1-$rx0)/$u}] [expr {($ry1-$ry0)/$u}] [um2 $bx] [um2 $rfbox] [expr {100*$rfbox/$bx}]]
}
set o
