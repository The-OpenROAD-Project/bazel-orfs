# The parent's blocks where the trap puts them: BLOCK_LOCS is a list of
# <instance> <x um> <y um> <orientation>. Origins are rounded up to the
# 0.144 x 2.16 um lattice that keeps asap7 M2-M5 pins on the parent's
# tracks. A block the list does not name is an error, not left to the
# macro placer: a trap's geometry is part of its answer.
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set named {}
foreach {name x y orient} $::env(BLOCK_LOCS) {
  set inst [$block findInst $name]
  if { $inst eq "NULL" } {
    # a block inside a flattened submodule: synthesis may keep its path
    # with dots rather than slashes
    set inst [$block findInst [string map {/ .} $name]]
  }
  if { $inst eq "NULL" } { error "place_blocks.tcl: no instance $name" }
  set sx [expr { int(ceil($x * $dbu / (0.144 * $dbu) - 1e-6)) * int(0.144 * $dbu) }]
  set sy [expr { int(ceil($y * $dbu / (2.16 * $dbu) - 1e-6)) * int(2.16 * $dbu) }]
  place_macro -macro_name [$inst getName] -location [list [expr { $sx / double($dbu) }] [expr { $sy / double($dbu) }]] -orientation $orient -exact
  puts "place_blocks.tcl: $name at [expr { $sx / double($dbu) }] [expr { $sy / double($dbu) }] $orient"
  lappend named [$inst getName]
}
foreach inst [$block getInsts] {
  if { [[$inst getMaster] isBlock] && [$inst getName] ni $named } {
    error "place_blocks.tcl: block [$inst getName] is not in BLOCK_LOCS"
  }
}
