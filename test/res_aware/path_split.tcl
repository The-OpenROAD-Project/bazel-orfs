# The worst register-to-register path at global route, split the way
# flow/designs/asap7/tage_update/README.md tabulates it: logic, repeaters
# and wire, with the clock latency taken out, plus how far the path
# travels against the distance between its ends, and where its nets'
# global-route guides are by layer. Sourced into an odb_debug daemon;
# `path_split` prints one JSON object.

proc ps_is_repeater { inst } {
  set master [[$inst getMaster] getName]
  return [regexp {^(BUF|INV|HB)} $master]
}

proc ps_pin_xy { pin } {
  set iterm [sta::sta_to_db_pin $pin]
  if { $iterm ne "NULL" } {
    lassign [$iterm getAvgXY] ok x y
    return [list $x $y]
  }
  set bterm [sta::sta_to_db_port [sta::pin_port $pin]]
  set box [[lindex [$bterm getBPins] 0] getBBox]
  return [list [$box xCenter] [$box yCenter]]
}

proc path_split { } {
  set path [lindex [find_timing_paths -path_delay max -group_path_count 1 \
    -sort_by_slack -path_group reg2reg] 0]
  if { $path eq "" } {
    error "path_split: no reg2reg path"
  }
  set points [get_property $path points]
  set start [get_property $path startpoint]
  # The data path begins at the startpoint, the launching clock pin;
  # everything before it is clock latency.
  set first -1
  for { set i 0 } { $i < [llength $points] } { incr i } {
    if { [get_property [lindex $points $i] pin] eq $start } {
      set first $i
      break
    }
  }
  if { $first < 0 } {
    error "path_split: startpoint not on the path"
  }
  set logic 0.0
  set logic_cells 0
  set rep 0.0
  set rep_cells 0
  set wire 0.0
  set travel 0
  set nets {}
  set prev_pin [get_property [lindex $points $first] pin]
  set prev_arr [get_property [lindex $points $first] arrival]
  for { set i [expr { $first + 1 }] } { $i < [llength $points] } { incr i } {
    set pt [lindex $points $i]
    set pin [get_property $pt pin]
    set arr [get_property $pt arrival]
    set d [expr { $arr - $prev_arr }]
    set prev_inst [sta::sta_to_db_inst [$prev_pin instance]]
    set inst [sta::sta_to_db_inst [$pin instance]]
    if { $prev_inst ne "NULL" && $prev_inst eq $inst } {
      if { [ps_is_repeater $inst] } {
        set rep [expr { $rep + $d }]
        incr rep_cells
      } else {
        set logic [expr { $logic + $d }]
        incr logic_cells
      }
    } else {
      set wire [expr { $wire + $d }]
      lassign [ps_pin_xy $prev_pin] x0 y0
      lassign [ps_pin_xy $pin] x1 y1
      set travel [expr { $travel + abs($x1 - $x0) + abs($y1 - $y0) }]
      lappend nets [sta::sta_to_db_net [$pin net]]
    }
    set prev_pin $pin
    set prev_arr $arr
  }
  set end [get_property [lindex $points end] pin]
  lassign [ps_pin_xy $start] xs ys
  lassign [ps_pin_xy $end] xe ye
  set span [expr { abs($xe - $xs) + abs($ye - $ys) }]

  # Guides are global route's boxes per layer; their long side, summed,
  # is where the path's wire went.
  set per_layer [dict create]
  foreach net [lsort -unique $nets] {
    foreach guide [$net getGuides] {
      set box [$guide getBox]
      set len [expr { max([$box dx], [$box dy]) }]
      dict incr per_layer [[$guide getLayer] getName] $len
    }
  }
  set layers {}
  dict for { layer len } $per_layer {
    lappend layers [od_jobj [list $layer [od_jnum [od_um $len]]]]
  }

  # A path end has no arrival of its own; its points do.
  set arrival [get_property [lindex $points end] arrival]
  set launch [get_property [lindex $points $first] arrival]
  return [od_jobj [list \
    slack [od_jnum [get_property $path slack]] \
    from [od_jstr [get_full_name $start]] \
    to [od_jstr [get_full_name $end]] \
    data_path [od_jnum [expr { $arrival - $launch }]] \
    logic [od_jnum $logic] logic_cells $logic_cells \
    repeaters [od_jnum $rep] repeater_cells $rep_cells \
    wire [od_jnum $wire] \
    travel_um [od_jnum [od_um $travel]] span_um [od_jnum [od_um $span]] \
    guides_um_by_layer [od_jarr $layers]]]
}
