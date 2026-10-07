set b [ord::get_db_block]; set u [expr double([$b getDbUnitsPerMicron])]
set die [$b getDieArea]; set W [expr [$die xMax]/$u]; set H [expr [$die yMax]/$u]
set nx 72; set ny 36; set dx [expr $W/$nx]; set dy [expr $H/$ny]
for {set j 0} {$j<$ny} {incr j} { for {set i 0} {$i<$nx} {incr i} { set g($i,$j) " "; set f($i,$j) 0 } }
proc mark {x0 y0 x1 y1 ch} { upvar g g dx dx dy dy nx nx ny ny
  for {set i [expr int($x0/$dx)]} {$i<=min($nx-1,int(($x1-0.001)/$dx))} {incr i} { for {set j [expr int($y0/$dy)]} {$j<=min($ny-1,int(($y1-0.001)/$dy))} {incr j} { set g($i,$j) $ch } } }
set c [$b getCoreArea]; mark [expr [$c xMin]/$u] [expr [$c yMin]/$u] [expr [$c xMax]/$u] [expr [$c yMax]/$u] "."
foreach o [$b getBlockages] { set bb [$o getBBox]; mark [expr [$bb xMin]/$u] [expr [$bb yMin]/$u] [expr [$bb xMax]/$u] [expr [$bb yMax]/$u] "h" }
set k 0; set leg ""
foreach i [$b getInsts] { if {![[$i getMaster] isBlock]} continue; set bb [$i getBBox]; set ch [string index "0123456789" [string index [$i getName] end]]; mark [expr [$bb xMin]/$u] [expr [$bb yMin]/$u] [expr [$bb xMax]/$u] [expr [$bb yMax]/$u] $ch; append leg "  $ch = [$i getName] [$i getOrient] ([format %.1f [expr [$bb xMin]/$u]],[format %.1f [expr [$bb yMin]/$u]])-([format %.1f [expr [$bb xMax]/$u]],[format %.1f [expr [$bb yMax]/$u]])\n" }
set fx0 1e9; set fy0 1e9; set fx1 0; set fy1 0; set n 0
foreach i [$b getInsts] { if {[$i getPlacementStatus] ne "FIRM" || ![string match riscv.dp/rf/* [$i getName]]} continue; incr n; set bb [$i getBBox]
  set ii [expr int(([$bb xMin]+[$bb xMax])/2/$u/$dx)]; set jj [expr int(([$bb yMin]+[$bb yMax])/2/$u/$dy)]; incr f($ii,$jj)
  set fx0 [expr min($fx0,[$bb xMin]/$u)]; set fy0 [expr min($fy0,[$bb yMin]/$u)]; set fx1 [expr max($fx1,[$bb xMax]/$u)]; set fy1 [expr max($fy1,[$bb yMax]/$u)] }
set o [format "die %.1f x %.1f um, core %.0f um2, 1 char = %.2f x %.2f um\n" $W $H [expr [$c dx]*[$c dy]/$u/$u] $dx $dy]
for {set j [expr $ny-1]} {$j>=0} {incr j -1} { set l [format "%5.1f |" [expr $j*$dy]]
  for {set i 0} {$i<$nx} {incr i} { set ch $g($i,$j); if {$f($i,$j)>0 && ![string is digit $ch]} { set ch [expr {$f($i,$j)>=12 ? "#" : "+"}] }; append l $ch }
  append o "$l|\n" }
append o $leg
append o [format "  # + = register file, %d FIRM cells, (%.1f,%.1f)-(%.1f,%.1f)\n  h = halo blockage   . = free core" $n $fx0 $fy0 $fx1 $fy1]
set o
