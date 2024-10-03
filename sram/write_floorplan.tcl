source $::env(SCRIPTS_DIR)/floorplan.tcl

set db [::ord::get_db]
set dbu_per_uu [expr double([[$db getTech] getDbUnitsPerMicron])]
set block [[$db getChip] getBlock]
set die_bbox [$block getDieArea]
set core_bbox [$block getCoreArea]
set scale [expr 1 / $dbu_per_uu]

set file [open [file join $::env(WORK_HOME) "floorplan.config"] w]
puts $file "export DIE_AREA=0 0 [expr $scale*[$die_bbox xMax]] [expr $scale*[$die_bbox yMax]]"
puts $file "export CORE_AREA=[expr $scale*[$core_bbox xMin]] [expr $scale*[$core_bbox yMin]]\
[expr $scale*([$die_bbox xMax] - ([$die_bbox xMax] - [$core_bbox xMax]))]\
[expr $scale*([$die_bbox yMax] - ([$die_bbox yMax] - [$core_bbox yMax]))]"
close $file
