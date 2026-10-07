set b [ord::get_db_block]; set u [$b getDbUnitsPerMicron]; set c [$b getCoreArea]; set a 0
foreach i [$b getInsts] { set m [$i getMaster]; if {[$m isBlock] || [string match *WELLTAP [$m getType]] || [string match *FILL* [$m getType]]} continue; set a [expr $a+double([$m getWidth])*[$m getHeight]/$u/$u] }
format "core %.0f um2, std cells %.0f um2" [expr double([$c dx])*[$c dy]/$u/$u] $a
