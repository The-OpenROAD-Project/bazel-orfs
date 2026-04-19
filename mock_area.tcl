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

set die_area "0 0 [expr $scale*[$die_bbox xMax]] [expr $scale*[$die_bbox yMax]]"
set core_area "[expr ([$core_bbox xMin] - [$die_bbox xMin]) / $dbu_per_uu] \
 [expr ([$core_bbox yMin] - [$die_bbox yMin]) / $dbu_per_uu] \
 [expr $scale*[$die_bbox xMax] - ([$die_bbox xMax] - [$core_bbox xMax]) / $dbu_per_uu ] \
 [expr $scale*[$die_bbox yMax] - ([$die_bbox yMax] - [$core_bbox yMax]) / $dbu_per_uu]"

set f [open $::env(OUTPUT) w]
puts $f "\{\"DIE_AREA\": \"$die_area\", \"CORE_AREA\": \"$core_area\", \"CORE_UTILIZATION\": \"\"\}"
close $f
