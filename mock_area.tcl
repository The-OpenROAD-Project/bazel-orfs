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

proc area_um {bbox} {
  global dbu_per_uu
  return "[expr [$bbox xMin] / $dbu_per_uu] [expr [$bbox yMin] / $dbu_per_uu] [expr [$bbox xMax] / $dbu_per_uu] [expr [$bbox yMax] / $dbu_per_uu]"
}

puts "DIE_AREA: [area_um $die_bbox]"
puts "CORE_AREA: [area_um $core_bbox]"

set file [open $out_file w]
tee $file "export DIE_AREA=0 0 [expr $scale*[$die_bbox xMax]] [expr $scale*[$die_bbox yMax]]"
# keep same margin between DIE_ARE and CORE_AREA
tee $file "export CORE_AREA=[expr ([$core_bbox xMin] - [$die_bbox xMin]) / $dbu_per_uu] \
 [expr ([$core_bbox yMin] - [$die_bbox yMin]) / $dbu_per_uu] \
 [expr $scale*[$die_bbox xMax] - ([$die_bbox xMax] - [$core_bbox xMax]) / $dbu_per_uu ] \
 [expr $scale*[$die_bbox yMax] - ([$die_bbox yMax] - [$core_bbox yMax]) / $dbu_per_uu]"
tee $file "export CORE_UTILIZATION="
close $file
