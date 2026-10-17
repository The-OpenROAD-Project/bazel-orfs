# What a pin trap is measured by, on a placed design (3_place.odb): a global
# route with congestion allowed and no repair iterations (wirelength and
# overflow as the router first sees them), and the side of the die every
# signal pin landed on, counted per port name (the part before '['), and
# where its pins sit on average. The
# same script measures a block and its parent; the tests add them up.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
set block [ord::get_db_block]
set die [$block getDieArea]
set sides [dict create]
set xs [dict create]
set ys [dict create]
foreach bterm [$block getBTerms] {
  if { [$bterm getSigType] ne "SIGNAL" } { continue }
  set box [$bterm getBBox]
  set cx [expr { ([$box xMin] + [$box xMax]) / 2 }]
  set cy [expr { ([$box yMin] + [$box yMax]) / 2 }]
  set d [dict create left [expr { $cx - [$die xMin] }] right [expr { [$die xMax] - $cx }] \
    bottom [expr { $cy - [$die yMin] }] top [expr { [$die yMax] - $cy }]]
  set side [lindex [lsort -stride 2 -index 1 -integer $d] 0]
  set port [lindex [split [$bterm getName] {[}] 0]
  dict update sides $port p { dict incr p $side }
  dict lappend xs $port [expr { double($cx - [$die xMin]) / [$die dx] }]
  dict lappend ys $port [expr { double($cy - [$die yMin]) / [$die dy] }]
}
set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
utl::redirectStringBegin
set ok [expr { ![catch { global_route -congestion_iterations 0 -allow_congestion -verbose } err] }]
set text [utl::redirectStringEnd]
puts $text
if { !$ok } { error "probe.tcl: global route failed: $err" }
set total_h 0; set total_v 0; set total_c 0; set usage 0
if { ![regexp -line {^Total\s+\d+\s+\d+\s+([\d.]+)%\s+(\d+)\s*/\s*(\d+)\s*/\s*(\d+)} $text - usage total_h total_v total_c] } {
  error "probe.tcl: no Total row in the global route report"
}
if { ![regexp {Total wirelength: (\d+) um} $text - wl] } {
  error "probe.tcl: no total wirelength in the global route report"
}
set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"design\": \"[$block getName]\","
puts $fp "  \"wirelength_um\": $wl,"
puts $fp "  \"usage_percent\": $usage,"
puts $fp "  \"max_h_overflow\": $total_h,"
puts $fp "  \"max_v_overflow\": $total_v,"
puts $fp "  \"total_overflow\": $total_c,"
puts $fp "  \"pin_sides\": {"
set ports [lsort [dict keys $sides]]
foreach port $ports {
  set p [dict get $sides $port]
  set fields {}
  foreach s {left right bottom top} {
    lappend fields "\"$s\": [expr { [dict exists $p $s] ? [dict get $p $s] : 0 }]"
  }
  puts $fp "    \"$port\": {[join $fields {, }]}[expr { $port eq [lindex $ports end] ? {} : {,} }]"
}
puts $fp "  },"
# where each port's pins sit, as the mean of their centres over the die's
# width and height: 0 is the west (south) edge, 1 the east (north)
puts $fp "  \"pin_centre\": {"
foreach port $ports {
  set mx [expr { [tcl::mathop::+ {*}[dict get $xs $port]] / [llength [dict get $xs $port]] }]
  set my [expr { [tcl::mathop::+ {*}[dict get $ys $port]] / [llength [dict get $ys $port]] }]
  puts $fp "    \"$port\": \[[format %.3f $mx], [format %.3f $my]\][expr { $port eq [lindex $ports end] ? {} : {,} }]"
}
puts $fp "  }"
puts $fp "}"
close $fp
