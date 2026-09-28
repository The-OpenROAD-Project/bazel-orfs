# Session-only: every register endpoint but the 32 setIdx_r[6] flops is a
# false path, so repair_timing works on this path's cone alone.
proc focus_path {} {
  set keep [get_cells -hier {*internalBanks_*entryWriteBuffer_io_write_*_bits_setIdx_r*6*}]
  set names {}
  foreach c $keep { dict set names [get_full_name $c] 1 }
  set others {}
  foreach c [all_registers -cells] {
    if {![dict exists $names [get_full_name $c]]} { lappend others $c }
  }
  set_false_path -to $others
  set_false_path -to [all_outputs]
  return "kept [llength $keep], false-pathed [llength $others]"
}
