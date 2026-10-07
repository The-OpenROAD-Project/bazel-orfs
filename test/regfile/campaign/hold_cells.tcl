# Hold repair's footprint at global route: the buffers repair_timing
# inserted for hold (named hold*) and their area.
set b [ord::get_db_block]; set u [$b getDbUnitsPerMicron]; set n 0; set a 0
foreach i [$b getInsts] {
  if {[string match hold* [$i getName]]} {
    incr n; set m [$i getMaster]
    set a [expr {$a + double([$m getWidth])*[$m getHeight]/$u/$u}]
  }
}
format "%d hold buffers, %.1f um2" $n $a
