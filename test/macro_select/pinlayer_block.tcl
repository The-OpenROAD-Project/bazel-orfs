# The pin-layer arms, block side: a zero-iteration global route on the
# placed block, the overflow over all of it and within EDGE_BAND_UM of
# its pin side (top), and its pins per layer.
#
#   OUTPUT_JSON        the result
#   CONGESTION_REPORT  FastRoute's regions over capacity
#   EDGE_BAND_UM       the band along the pin side
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set top [expr { [[$block getDieArea] yMax] / double($dbu) }]
set layers [dict create]
foreach bt [$block getBTerms] {
  foreach bp [$bt getBPins] {
    foreach box [$bp getBoxes] {
      dict incr layers [[$box getTechLayer] getName]
    }
  }
}
set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
utl::redirectStringBegin
catch { global_route -congestion_iterations 0 -allow_congestion -verbose \
  -congestion_report_file $::env(CONGESTION_REPORT) } err
set text [utl::redirectStringEnd]
puts $text
set total_h 0; set total_v 0; set total_c 0; set usage 0
regexp -line {^Total\s+\d+\s+\d+\s+([\d.]+)%\s+(\d+)\s*/\s*(\d+)\s*/\s*(\d+)} $text - usage total_h total_v total_c
set band $::env(EDGE_BAND_UM)
set edge 0
set edge_regions 0
if { [file exists $::env(CONGESTION_REPORT)] } {
  set fp [open $::env(CONGESTION_REPORT) r]
  set over 1
  while { [gets $fp line] >= 0 } {
    regexp {congestion:\s*(-?\d+)} $line - over
    if { [regexp {bbox = \(\s*([-\d.]+),\s*([-\d.]+)\s*\) - \(\s*([-\d.]+),\s*([-\d.]+)\s*\)} $line - x0 y0 x1 y1] } {
      if { $y1 >= $top - $band } {
        incr edge $over
        incr edge_regions
      }
      set over 1
    }
  }
  close $fp
} else {
  close [open $::env(CONGESTION_REPORT) w]
}
set fp [open $::env(OUTPUT_JSON) w]
set pl {}
dict for {l n} $layers { lappend pl "\"$l\": $n" }
puts $fp "{"
puts $fp "  \"usage_percent\": $usage,"
puts $fp "  \"overflow_h\": $total_h,"
puts $fp "  \"overflow_v\": $total_v,"
puts $fp "  \"total_congestion\": $total_c,"
puts $fp "  \"edge_band_um\": $band,"
puts $fp "  \"edge_overflow\": $edge,"
puts $fp "  \"edge_regions\": $edge_regions,"
puts $fp "  \"pins_per_layer\": {[join $pl {, }]}"
puts $fp "}"
close $fp
