# Every signal pin of the block on its top side: the side that faces the
# parent's logic when the parent places the block at its bottom, R0.
set names {}
foreach bterm [[ord::get_db_block] getBTerms] {
  if { [$bterm getSigType] ne "SIGNAL" && [$bterm getSigType] ne "CLOCK" } { continue }
  lappend names [$bterm getName]
}
set_io_pin_constraint -region top:* -pin_names $names
puts "pins_top.tcl: [llength $names] pins on the top side"
