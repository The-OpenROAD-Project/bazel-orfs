# The pin-layer arms, parent side: a global route of the parent at CTS,
# its vias and wire, and the wire delay of the nets on the block's pins
# (driver to load across the channel) from the routes' parasitics.
#
#   OUTPUT_JSON   the result
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb
set block [ord::get_db_block]
set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
utl::redirectStringBegin
global_route -verbose
set text [utl::redirectStringEnd]
puts $text
set vias 0
regexp -nocase {vias:\s*(\d+)} $text - vias
set wl 0
regexp {Total wirelength: (\d+) um} $text - wl
estimate_parasitics -global_routing
set macro ""
foreach inst [$block getInsts] {
  if { [[$inst getMaster] isBlock] } { set macro [$inst getName] }
}
set pins [get_pins $macro/*]
set ui_ps [expr { [sta::time_ui_sta 1.0] * 1e12 }]
set wires {}
foreach pe [find_timing_paths -through $pins -unconstrained -path_delay max \
  -group_path_count 100000 -endpoint_path_count 1] {
  set pts [get_property $pe points]
  for { set i 0 } { $i < [llength $pts] } { incr i } {
    set pin [get_property [lindex $pts $i] pin]
    if { [get_property $pin is_port] } { continue }
    if { [get_full_name [get_cells -of_objects $pin]] ne $macro } { continue }
    if { [get_property $pin direction] eq "output" && $i + 1 < [llength $pts] } {
      set a [get_property [lindex $pts $i] arrival]
      set b [get_property [lindex $pts [expr { $i + 1 }]] arrival]
    } elseif { $i > 0 } {
      set a [get_property [lindex $pts [expr { $i - 1 }]] arrival]
      set b [get_property [lindex $pts $i] arrival]
    } else {
      continue
    }
    lappend wires [expr { ($b - $a) * $ui_ps }]
    break
  }
}
set n [llength $wires]
set max 0.0
set sum 0.0
foreach w $wires { set max [expr { max($max, $w) }]; set sum [expr { $sum + $w }] }
set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"vias\": $vias,"
puts $fp "  \"wirelength_um\": $wl,"
puts $fp "  \"pin_nets\": $n,"
puts $fp "  \"wire_ps_max\": [format %.2f $max],"
puts $fp "  \"wire_ps_mean\": [format %.2f [expr { $n ? $sum / $n : 0.0 }]]"
puts $fp "}"
close $fp
