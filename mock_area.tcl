proc tee {file content} {
	puts $content
	puts $file $content
}

set out_file [file join $::env(WORK_HOME) $::env(OUTPUT)]

read_db $::env(RESULTS_DIR)/2_floorplan.odb
set db [::ord::get_db]
set dbu_per_uu [expr double([[$db getTech] getDbUnitsPerMicron])]
set block [[$db getChip] getBlock]
set die_bbox [$block getDieArea]
set core_bbox [$block getCoreArea]
set scale [expr $::env(MOCK_AREA) / $dbu_per_uu]

set file [open $out_file w]
tee $file "export DIE_AREA=0 0 [expr $scale*[$die_bbox xMax]] [expr $scale*[$die_bbox yMax]]"
tee $file "export CORE_AREA=[expr $scale*[$core_bbox xMin]] [expr $scale*[$core_bbox yMin]]\
[expr $scale*([$die_bbox xMax] - ([$die_bbox xMax] - [$core_bbox xMax]))]\
[expr $scale*([$die_bbox yMax] - ([$die_bbox yMax] - [$core_bbox yMax]))]"
tee $file "export CORE_UTILIZATION="
close $file
