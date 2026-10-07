read_db $::env(ODB_FILE)
set b [ord::get_db_block]; set n 0; set dt 0; set nets 0
foreach i [$b getInsts] {
  if {![string match riscv.dp/rf/* [$i getName]] || [string match *TAP* [[$i getMaster] getName]]} continue
  if {[$i getPlacementStatus] ne "NONE"} { $i setPlacementStatus NONE; incr n }
  if {[$i isDoNotTouch]} { $i setDoNotTouch 0; incr dt }
}
foreach net [$b getNets] { if {[string match riscv.dp/rf/* [$net getName]] && [$net isDoNotTouch]} { $net setDoNotTouch 0; incr nets } }
puts "unplaced $n, cleared dont_touch on $dt insts and $nets nets"
write_db $::env(ODB_FILE)
