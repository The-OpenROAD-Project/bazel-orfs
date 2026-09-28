# Put every load of the start flop but the path's XNOR behind one buffer,
# through the odb API (insert_buffer -load_pins crashes this build).
proc split_start_flop {cell} {
  set block [ord::get_db_block]
  set flop [sta::sta_to_db_inst [get_cells {t1_startPcVec_0_addr*13*}]]
  set qn [$flop findITerm QN]
  set net [$qn getNet]
  set master [[ord::get_db] findMaster $cell]
  set buf [odb::dbInst_create $block $master split_start_buf]
  set out [odb::dbNet_create $block split_start_net]
  set n 0
  foreach it [$net getITerms] {
    if {[$it isOutputSignal]} { continue }
    if {[[$it getInst] getName] eq {_366659_}} { continue }
    $it disconnect; $it connect $out; incr n
  }
  [$buf findITerm A] connect $net
  [$buf findITerm Y] connect $out
  set l [$flop getLocation]
  $buf setLocation [lindex $l 0] [lindex $l 1]
  $buf setPlacementStatus PLACED
  return "moved $n loads behind $cell"
}
