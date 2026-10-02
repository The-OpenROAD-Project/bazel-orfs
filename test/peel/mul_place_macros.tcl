# The four multipliers (or their peeled cores) in the corners of the
# die, the adder tree's logic between them: every macro output crosses
# to the middle.
set block [ord::get_db_block]
set insts {}
foreach inst [$block getInsts] {
  if { [[$inst getMaster] getName] in {mul mul_core} } { lappend insts $inst }
}
set insts [lsort -command { apply {{a b} { string compare [$a getName] [$b getName] }} } $insts]
if { [llength $insts] != 4 } {
  utl::error FLW 1 "mul_place_macros.tcl: [llength $insts] multipliers, expected four"
}
foreach inst $insts {x y} {10 10 10 190 190 10 190 190} {
  place_macro -macro_name [$inst getName] -location [list $x $y] -orientation R0
  $inst setPlacementStatus FIRM
}
