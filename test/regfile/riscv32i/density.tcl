set b [ord::get_db_block]; set u [expr double([$b getDbUnitsPerMicron])]
set site 54; set rowh 270
set x0 1e12; set y0 1e12; set x1 0; set y1 0; set area 0; set tap 0; set n 0
set kinds [dict create]
set byrow [dict create]
foreach i [$b getInsts] { if {[$i getPlacementStatus] ne "FIRM" || ![string match riscv.dp/rf/* [$i getName]]} continue
  set bb [$i getBBox]; set m [$i getMaster]; set a [expr double([expr {[$bb xMax]-[$bb xMin]}])*[expr {[$bb yMax]-[$bb yMin]}]]
  set x0 [expr min($x0,[$bb xMin])]; set y0 [expr min($y0,[$bb yMin])]; set x1 [expr max($x1,[$bb xMax])]; set y1 [expr max($y1,[$bb yMax])]
  if {[string match *TAP* [$m getName]]} {set tap [expr $tap+$a]} else {set area [expr $area+$a]; incr n}
  dict set kinds [$m getName] [expr {[dict exists $kinds [$m getName]] ? [dict get $kinds [$m getName]]+[expr {[$bb xMax]-[$bb xMin]}]/$site : [expr {[$bb xMax]-[$bb xMin]}]/$site}]
  dict lappend byrow [$bb yMin] [list [$bb xMin] [$bb xMax]] }
set box [expr double($x1-$x0)*($y1-$y0)]
# gaps per row inside the box
set small 0; set big 0; set nbig 0
dict for {y l} $byrow { set l [lsort -integer -index 0 $l]; set prev $x0
  foreach e $l { set gap [expr [lindex $e 0]-$prev]; if {$gap > 0} { if {$gap >= 10*$site} {set big [expr $big+$gap]; incr nbig} else {set small [expr $small+$gap]} }; set prev [expr max($prev,[lindex $e 1])] }
  set gap [expr $x1-$prev]; if {$gap >= 10*$site} {set big [expr $big+$gap]} else {set small [expr $small+$gap]} }
set rows [dict size $byrow]
set o [format "array box %.1f x %.1f um = %.0f um2, %d rows\n" [expr ($x1-$x0)/$u] [expr ($y1-$y0)/$u] [expr $box/$u/$u] $rows]
append o [format "cells %d: %.0f um2 (%.0f%%), taps %.0f um2 (%.1f%%)\n" $n [expr $area/$u/$u] [expr 100*$area/$box] [expr $tap/$u/$u] [expr 100*$tap/$box]]
append o [format "empty in rows: small gaps (<10 sites, tile slack) %.0f um2 (%.0f%%), wide gaps (>=10 sites: service columns, row ends) %.0f um2 (%.0f%%)\n" [expr $small*$rowh/$u/$u] [expr 100*$small*$rowh/$box] [expr $big*$rowh/$u/$u] [expr 100*$big*$rowh/$box]]
append o "sites per master: [lsort -stride 2 -index 1 -integer -decreasing $kinds]"
set o
