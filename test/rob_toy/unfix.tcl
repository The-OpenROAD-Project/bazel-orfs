# After global placement (POST_GLOBAL_PLACE_TCL): the generated cells
# place.tcl made FIRM become PLACED, so repair can resize them and the
# legaliser move them.
set n 0
foreach inst [[ord::get_db_block] getInsts] {
  if { [regexp {b\d+_l\d+_c\d+} [$inst getName]] && [$inst isFixed] } {
    $inst setPlacementStatus PLACED
    incr n
  }
}
puts "unfix.tcl: $n generated cells made PLACED"
