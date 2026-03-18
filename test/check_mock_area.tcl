source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

set macros [find_macros]
if {[llength $macros] != 1} {
  puts "Expected exactly one macro, but found [llength $macros]"
  exit 1
}

set tag_array_64x184 [lindex [find_macros] 0]
set bbox [$tag_array_64x184 getBBox]
set width [ord::dbu_to_microns [$bbox getDX]]
set height [ord::dbu_to_microns [$bbox getDY]]

# Verify the macro has nonzero area and a tall aspect ratio (CORE_ASPECT_RATIO=10)
if {$width <= 0 || $height <= 0} {
  puts "Macro has zero dimension: width=$width height=$height"
  exit 1
}
set aspect_ratio [expr {$height / $width}]
if {$aspect_ratio < 5} {
  puts "Expected tall aspect ratio (>=5), got $aspect_ratio (width=$width height=$height)"
  exit 1
}

puts "Macro dimensions OK: width=$width height=$height aspect_ratio=$aspect_ratio"
exec touch $::env(WORK_HOME)/area_ok.txt
