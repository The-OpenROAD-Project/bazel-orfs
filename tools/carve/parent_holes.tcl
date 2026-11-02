# The floorplan of a parent macro (evert.tcl cut the blocks out of its
# synthesis): the whole die, with a hole where each block sits. No cell
# of the parent's is placed and no wire of its routed in a hole. Each parent
# port for a block pin goes where the plan puts that pin, mirrored across
# the hole's edge onto the parent's side, on the same layer, so the two
# abut pin on pin.
#
# Everything here is the plan's, in git; nothing of a block's build is
# read, so the parent and the blocks build side by side.
#
# Sourced as IO_CONSTRAINTS, after the floorplan is initialized.
#
#   HOLES        master x y w h, per block, in um: where the top level puts it, R0
#   PLAN_PINS    each block's plan pins file (plan_floorplan.py), the pin table

# ORFS sources this from inside a proc; the procs below want globals
if { [info level] > 0 } {
  uplevel #0 [list source [info script]]
  return
}
set block [ord::get_db_block]
set tech [ord::get_db_tech]
set dbu [$tech getDbUnitsPerMicron]

proc um { v } {
  return [expr { int(round($v * $::dbu)) }]
}

# master -> {x0 y0 x1 y1} in dbu
set holes [dict create]
foreach {master x y w h} $::env(HOLES) {
  set x0 [um $x]
  set y0 [um $y]
  dict set holes $master [list $x0 $y0 [expr { $x0 + [um $w] }] [expr { $y0 + [um $h] }]]
}
# Each hole is a block at its own outline, so the plan must have laid out
# outlines: a plan that laid out smaller footprints (block_density) put
# XSTile's holes over each other and past the die, which global route
# found two hours later (GRT-0209, a pin outside the die).
set die [$block getDieArea]
set names [dict keys $holes]
foreach a $names {
  lassign [dict get $holes $a] ax0 ay0 ax1 ay1
  if { $ax0 < [$die xMin] || $ay0 < [$die yMin] || $ax1 > [$die xMax] || $ay1 > [$die yMax] } {
    utl::error FLW 13 "parent_holes: the hole for $a leaves the die"
  }
  foreach b [lrange $names [expr { [lsearch -exact $names $a] + 1 }] end] {
    lassign [dict get $holes $b] bx0 by0 bx1 by1
    if { $ax0 < $bx1 && $bx0 < $ax1 && $ay0 < $by1 && $by0 < $ay1 } {
      utl::error FLW 14 "parent_holes: the holes for $a and $b overlap"
    }
  }
}

# the plan's pin tables, ::plan_pins(<master>): pin layer x y w h, um,
# in the block's frame, each a pin's centre and size
set ::plan_pins_only 1
foreach f $::env(PLAN_PINS) {
  source $f
}
unset ::plan_pins_only
dict for {master box} $holes {
  if { ![info exists ::plan_pins($master)] } {
    utl::error FLW 10 "parent_holes: no plan pins file names $master"
  }
}

proc obstruct { x0 y0 x1 y1 } {
  odb::dbBlockage_create $::block $x0 $y0 $x1 $y1
  foreach layer [$::tech getLayers] {
    if { [$layer getType] eq "ROUTING" } {
      odb::dbObstruction_create $::block $layer $x0 $y0 $x1 $y1
    }
  }
}

# a row that runs through a box or within halo of it is cut at its edges
proc cut_rows { x0 y0 x1 y1 halo } {
  foreach row [$::block getRows] {
    set b [$row getBBox]
    if { [$b yMax] <= $y0 - $halo || [$b yMin] >= $y1 + $halo } { continue }
    if { [$b xMax] <= $x0 - $halo || [$b xMin] >= $x1 + $halo } { continue }
    set site [$row getSite]
    set sw [$site getWidth]
    lassign [$row getOrigin] ox oy
    set name [$row getName]
    set orient [$row getOrient]
    set end [$b xMax]
    odb::dbRow_destroy $row
    set n [expr { ($x0 - $halo - $ox) / $sw }]
    if { $n > 0 } {
      odb::dbRow_create $::block ${name}_w $site $ox $oy $orient HORIZONTAL $n $sw
    }
    set xr [expr { $ox + (($x1 + $halo - $ox + $sw - 1) / $sw) * $sw }]
    set n [expr { ($end - $xr) / $sw }]
    if { $n > 0 } {
      odb::dbRow_create $::block ${name}_e $site $xr $oy $orient HORIZONTAL $n $sw
    }
  }
}

set halo [um 0.54]
dict for {master box} $holes {
  obstruct {*}$box
  cut_rows {*}$box $halo
}

# a plan pin's centre mirrored across the edge of its block it lies on,
# in die dbu: the two touch there, the parent's outside the hole
proc mirrored { master row } {
  lassign [dict get $::holes $master] hx0 hy0 hx1 hy1
  lassign $row pin layer x y w h
  set W [expr { ($hx1 - $hx0) / double($::dbu) }]
  set H [expr { ($hy1 - $hy0) / double($::dbu) }]
  if { $y - $h / 2.0 <= 1e-6 } {
    set y [expr { -$y }]
    set side bottom
  } elseif { $y + $h / 2.0 >= $H - 1e-6 } {
    set y [expr { 2 * $H - $y }]
    set side top
  } elseif { $x - $w / 2.0 <= 1e-6 } {
    set x [expr { -$x }]
    set side left
  } elseif { $x + $w / 2.0 >= $W - 1e-6 } {
    set x [expr { 2 * $W - $x }]
    set side right
  } else {
    utl::error FLW 11 "parent_holes: $master/$pin is on no edge of the plan's outline"
  }
  return [list [expr { $hx0 + [um $x] }] [expr { $hy0 + [um $y] }] $layer [um $w] [um $h] $side]
}

# the parent's port for block pin <pin> of <master> is u_<master>__<pin>
set placed 0
set block_port [dict create]
dict for {master box} $holes {
  set rows [dict create]
  foreach {pin layer x y w h} $::plan_pins($master) {
    dict set rows $pin [list $pin $layer $x $y $w $h]
  }
  set prefix "u_${master}__"
  foreach bt [$block getBTerms] {
    set port [$bt getName]
    if { [string first $prefix $port] != 0 } { continue }
    set pin [string range $port [string length $prefix] end]
    if { ![dict exists $rows $pin] } {
      utl::error FLW 12 "parent_holes: the plan places no pin $pin on $master (port $port)"
    }
    lassign [mirrored $master [dict get $rows $pin]] x y layer w h
    place_pin -pin_name $port -layer $layer \
      -location [list [expr { $x / double($dbu) }] [expr { $y / double($dbu) }]] \
      -pin_size [list [expr { $w / double($dbu) }] [expr { $h / double($dbu) }]]
    dict set block_port $port 1
    incr placed
  }
}

puts "parent_holes: [dict size $holes] holes, $placed block pins placed"

# the parent's own ports: everything else, on the bottom edge, over the
# top level's strip
set own {}
foreach bt [$block getBTerms] {
  if { [dict exists $block_port [$bt getName]] } { continue }
  lappend own [$bt getName]
}
set_io_pin_constraint -region bottom:* -pin_names $own
puts "parent_holes: [llength $own] own ports on the bottom edge"
