# A top level whose tiles' abstracts have exact shapes: the layers under
# MIN_CLK_ROUTING_LAYER over the parent's notch, where the tiles are,
# are the tiles' own, whose signals use them once routed; an abstract
# written at global route holds none of those wires yet. Global routing
# at the top gets no capacity there, so its wires cross the tiles on
# the clock's layers only. Its clock tree's leaves are signals to grt
# (only inner clock nets get the clock's layers), hence the region and
# not the layer range. PARENT_Y, when set, is how far the macros sit
# off the die's bottom edge (place_notch.tcl).
set py [expr { [info exists ::env(PARENT_Y)] ? $::env(PARENT_Y) : 0 }]
set box [list $::env(NOTCH_X0) [expr { $py + $::env(NOTCH_Y0) }] \
  $::env(NOTCH_X1) [expr { $py + $::env(NOTCH_Y1) }]]
set tech [ord::get_db_tech]
set lo [[$tech findLayer $::env(MIN_ROUTING_LAYER)] getRoutingLevel]
set hi [[$tech findLayer $::env(MIN_CLK_ROUTING_LAYER)] getRoutingLevel]
set layers {}
foreach layer [$tech getLayers] {
  if { [$layer getType] ne "ROUTING" } { continue }
  set level [$layer getRoutingLevel]
  if { $level < $lo || $level >= $hi } { continue }
  set_global_routing_region_adjustment $box -layer [$layer getName] -adjustment 1.0
  lappend layers [$layer getName]
}
puts "grt_notch.tcl: no capacity on $layers over the notch, $box um"
