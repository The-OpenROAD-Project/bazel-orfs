set b [ord::get_db_block]; set u [expr double([$b getDbUnitsPerMicron])]
set x0 1e12; set y0 1e12; set x1 0; set y1 0
foreach i [$b getInsts] { if {[$i getPlacementStatus] ne "FIRM" || ![string match riscv.dp/rf/* [$i getName]]} continue; set bb [$i getBBox]
  set x0 [expr min($x0,[$bb xMin])]; set y0 [expr min($y0,[$bb yMin])]; set x1 [expr max($x1,[$bb xMax])]; set y1 [expr max($y1,[$bb yMax])] }
set box [expr double($x1-$x0)*($y1-$y0)]
set firm 0; set other [dict create]; set oa 0
foreach i [$b getInsts] { set m [$i getMaster]; if {[$m isBlock]} continue; set bb [$i getBBox]
  set ix0 [expr max($x0,[$bb xMin])]; set ix1 [expr min($x1,[$bb xMax])]; set iy0 [expr max($y0,[$bb yMin])]; set iy1 [expr min($y1,[$bb yMax])]
  if {$ix1 <= $ix0 || $iy1 <= $iy0} continue
  set a [expr double($ix1-$ix0)*($iy1-$iy0)]
  if {[$i getPlacementStatus] eq "FIRM" && [string match riscv.dp/rf/* [$i getName]]} { set firm [expr $firm+$a]; continue }
  set n [$i getName]
  if {[string match riscv.dp/rf/* $n]} {set k "array decode (periphery)"} elseif {[string match *WELLTAP* [$m getType]] || [string match TAP_* $n] || [string match PHY_* $n]} {set k "taps/endcaps"} elseif {[regexp {(^|/)(place|rebuffer|split|clone|input|output|wire|max_|repair)} $n]} {set k "resizer buffers"} else {set k "other logic"}
  dict set other $k [expr {[dict exists $other $k] ? [dict get $other $k]+$a : $a}]; set oa [expr $oa+$a] }
set empty0 [expr $box-$firm]
set o [format "array box %.0f um2: array cells %.0f (%.0f%%), empty before place %.0f um2\n" [expr $box/$u/$u] [expr $firm/$u/$u] [expr 100*$firm/$box] [expr $empty0/$u/$u]]
dict for {k a} $other { append o [format "  filled by %-26s %5.0f um2 (%4.1f%% of the empty space)\n" $k [expr $a/$u/$u] [expr 100*$a/$empty0]] }
append o [format "  total filled %.0f um2 = %.0f%% of the empty space; box now %.0f%% full" [expr $oa/$u/$u] [expr 100*$oa/$empty0] [expr 100*($firm+$oa)/$box]]
set o
