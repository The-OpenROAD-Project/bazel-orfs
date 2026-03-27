source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

set macros [find_macros]
if {[llength $macros] == 0} {
  puts "Expected at least one macro, but found none"
  exit 1
}

foreach macro $macros {
  set name [$macro getName]
  set bbox [$macro getBBox]
  set width [ord::dbu_to_microns [$bbox getDX]]
  set height [ord::dbu_to_microns [$bbox getDY]]

  if {$width <= 0 || $height <= 0} {
    puts "Macro $name has zero dimension: width=$width height=$height"
    exit 1
  }

  puts "Macro $name: width=$width height=$height"
}

puts "All [llength $macros] macro(s) have valid dimensions"
exec touch $::env(WORK_HOME)/area_ok.txt
