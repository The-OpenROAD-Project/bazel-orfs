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
# block pins off the parent's tracks: a pin on a vertical layer whose
# centre is not on one of the parent's x tracks of that layer (a horizontal
# one, y), as a block flipped in the parent can leave them (pin trap 7)
set offtrack 0
set blockpins 0
foreach inst [$block getInsts] {
  if { ![[$inst getMaster] isBlock] } { continue }
  foreach iterm [$inst getITerms] {
    if { [$iterm getSigType] ne "SIGNAL" } { continue }
    set mpins [[$iterm getMTerm] getMPins]
    if { [llength $mpins] == 0 } { continue }
    set layer [[lindex [[lindex $mpins 0] getGeometry] 0] getTechLayer]
    if { $layer eq "NULL" || [$layer getType] ne "ROUTING" } { continue }
    set grid [$block findTrackGrid $layer]
    if { $grid eq "NULL" } { continue }
    # the pin's placed box: one shape per pin in a block's abstract
    set box [$iterm getBBox]
    incr blockpins
    if { [$layer getDirection] eq "VERTICAL" } {
      set c [expr { ([$box xMin] + [$box xMax]) / 2 }]
      set tracks [$grid getGridX]
    } else {
      set c [expr { ([$box yMin] + [$box yMax]) / 2 }]
      set tracks [$grid getGridY]
    }
    if { [lsearch -exact -integer -sorted $tracks $c] < 0 } { incr offtrack }
  }
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
# timing, when PROBE_TIMING asks: the worst setup path with placement
# parasitics, its slack, the period less that slack, and the blocks the
# path crosses from an input pin to an output pin (an in2out arc of the
# block's timing model): a block on the worst path that way is a path no
# placement of the parent removes
set timing ""
if { [info exists ::env(PROBE_TIMING)] && $::env(PROBE_TIMING) } {
  estimate_parasitics -placement
  set pe [lindex [find_timing_paths -path_delay max -group_path_count 1 -sort_by_slack] 0]
  if { $pe eq "" } { error "probe.tcl: no setup path to report" }
  set slack [get_property $pe slack]
  set period [get_property [lindex [all_clocks] 0] period]
  set crossed {}
  set prev ""
  foreach pt [get_property $pe points] {
    set name [get_full_name [get_property $pt pin]]
    set i [string last / $name]
    if { $i > 0 } {
      set inst [$block findInst [string range $name 0 [expr { $i - 1 }]]]
      if { $inst ne "NULL" && [[$inst getMaster] isBlock] } {
        set iterm [$inst findITerm [string range $name [expr { $i + 1 }] end]]
        if { $prev ne "" && [lindex $prev 0] eq [$inst getName] && [lindex $prev 1] eq "INPUT" && [$iterm getIoType] eq "OUTPUT" } {
          lappend crossed [$inst getName]
        }
        set prev [list [$inst getName] [$iterm getIoType]]
        continue
      }
    }
    set prev ""
  }
  set timing [format {"slack_ps": %.1f, "period_ps": %.1f, "min_period_ps": %.1f, "startpoint": "%s", "endpoint": "%s", "in2out_blocks": [%s]} \
    $slack $period [expr { $period - $slack }] \
    [get_full_name [get_property $pe startpoint]] [get_full_name [get_property $pe endpoint]] \
    [join [lmap c $crossed { string cat {"} $c {"} }] {, }]]
}
# pin access, as the flow's global route stage runs it before routing: a
# pin it finds no access point for stops it (DRT-0073)
set access "not run"
if { [info exists ::env(PROBE_PIN_ACCESS)] && $::env(PROBE_PIN_ACCESS) } {
  if { [catch { pin_access } err] } {
    regsub -all {"} [lindex [split $err "\n"] 0] {'} access
  } else {
    set access "ok"
  }
}
set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"design\": \"[$block getName]\","
puts $fp "  \"wirelength_um\": $wl,"
puts $fp "  \"usage_percent\": $usage,"
puts $fp "  \"max_h_overflow\": $total_h,"
puts $fp "  \"max_v_overflow\": $total_v,"
puts $fp "  \"total_overflow\": $total_c,"
puts $fp "  \"block_pin_shapes\": $blockpins,"
puts $fp "  \"block_pins_off_track\": $offtrack,"
puts $fp "  \"pin_access\": \"$access\","
if { $timing ne "" } { puts $fp "  \"timing\": {$timing}," }
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
