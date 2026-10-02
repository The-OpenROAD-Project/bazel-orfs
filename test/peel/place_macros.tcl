# Src (or its peeled core) in the bottom-left corner, Dst in the top
# right: the crossing between them is the parent's to fill.
set block [ord::get_db_block]
foreach {masters x y} {
  {Src Src_core} 10.0 10.0
  {Dst} 160.0 160.0
} {
  set insts {}
  foreach inst [$block getInsts] {
    if { [lsearch -exact $masters [[$inst getMaster] getName]] >= 0 } { lappend insts $inst }
  }
  if { [llength $insts] != 1 } {
    utl::error FLW 1 "place_macros.tcl: [llength $insts] instances of $masters, expected one"
  }
  place_macro -macro_name [[lindex $insts 0] getName] -location [list $x $y] -orientation R0
  [lindex $insts 0] setPlacementStatus FIRM
}
