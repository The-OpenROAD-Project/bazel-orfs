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

proc expect {value a b} {
  if {$a != $b} {
    puts "Expected $value $a == $b"
    exit 1
  }
}
expect Width $width 20.364
expect Height $height 39.128

exec touch $::env(WORK_HOME)/area_ok.txt
