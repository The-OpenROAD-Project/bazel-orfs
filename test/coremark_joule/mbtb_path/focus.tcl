# Session-only: every timing check endpoint but the path's setIdx[6]
# registers is a false path (register data pins, clock-gate enables,
# macro inputs, outputs), so repair_timing works on this path's cone alone.
proc focus_path {} {
  set keep {}
  foreach c [get_cells -hier {*internalBanks_*io_write_*_bits_setIdx*6*}] {
    foreach p [get_pins -of_objects $c -filter {direction == input}] { dict set keep [get_full_name $p] 1 }
  }
  set macro_pins {}
  foreach i [[ord::get_db_block] getInsts] {
    if {[[$i getMaster] isBlock]} {
      foreach p [get_pins -quiet -of_objects [get_cells -quiet [string map {[ \\[ ] \\]} [$i getName]]] -filter {direction == input}] { lappend macro_pins $p }
    }
  }
  set others {}
  foreach p [concat [all_registers -data_pins] [all_registers -level_sensitive -data_pins] [get_pins -quiet -hier */ENA] $macro_pins] {
    if {![dict exists $keep [get_full_name $p]]} { lappend others $p }
  }
  set_false_path -to $others
  set_false_path -to [all_outputs]
  return "kept [dict size $keep] pins, false-pathed [llength $others]"
}
