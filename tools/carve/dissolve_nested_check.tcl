# The macros nested in the parent or a block that the Top dissolved
# (parent_macro.bzl's dissolve_nested, dissolve_nested.tcl), checked on
# the first pass's routed Top (<pm>_dissolve_nested, whole_check): for each
# master,
#   - the place its parent or block gave it, as the database records the
#     dissolve, is where that macro's own global route put its instance
#     (the parent at the die's origin, a block at its hole);
#   - every cell of its own flow's global route is there, but the clock
#     buffers the strip took (TIMING cells whose input is on a clock net
#     of the source), at the place that flow gave it through the
#     instance's place and orientation, all moved by one step of less than
#     a site across and at most a row up or down, and LOCKED;
#   - every cell on the Top's rows and sites, in a row of its orientation;
#   - every supply pin of every cell on its net and touching one of that
#     net's special wires: the Top's power grid runs along its rails;
#   - every register clocked, each driven by a buffer or inverter of the
#     Top's clock tree (TIMING, outside the dissolved module), none on a
#     port's net, the clock port's included, and none counted as clocked
#     on a supply net.
# A broken rule stops the check (FLW 148). Each stop of dissolve_nested.tcl
# from FLW 140 to FLW 147 then fires on purpose, each for its own reason,
# its message read back; a control that does not stop, or stops for
# another reason, stops the check too. A probe is an instance of the
# first master's macro at the place and in the orientation its parent
# gave it:
#   absent      a master with no instance (FLW 141)
#   odb         a master given another flow's database (FLW 140)
#   no_clock    a probe with nothing on its pins dissolved (FLW 142)
#   off_row     a cell moved a dbu off its row (FLW 144)
#   flipped     a cell turned over in its row (FLW 144)
#   unplaced    a register of a dissolved probe unplaced (FLW 143)
#   fewer       that register destroyed (FLW 145)
#   unclocked   a probe, its clock pin on a net, dissolved with its own
#               clock tree kept (FLW 146)
#   supply      a cell's supply pin disconnected (FLW 147)
# FLW 149 (no module instance) and FLW 150 (a net on the pins gone
# without a feedthrough) have none: dbInst::dissolve (patch 0171) cannot
# be made to break its own contract from here.
# Last, the orientations the first master was not given: its database
# dissolved again, unconnected, at the place its parent gave it, mirrored
# MX, MY and R180 (XSTile's register files sit R0, MX and MY), each must
# land on the Top's rows in their orientation with every cell where its
# flow placed it through that orientation, by dissolve_nested.tcl's move.
#
#   TOP_DIR      the first pass's run, 5_top_grt.odb in it
#   DISSOLVE_NESTED_MASTERS, DISSOLVE_NESTED_ODBS, DISSOLVE_NESTED_CLOCKS,
#   DISSOLVE_NESTED_TCL      as the Top's floorplan reads them
#   DISSOLVE_MASTERS, DISSOLVE_ODBS, HOLES   the parent and the blocks,
#                as the Top's floorplan reads them
#   NESTED_TXT   the counts and the controls, "key value" lines
source $::env(SCRIPTS_DIR)/load.tcl
set ::env(RESULTS_DIR) $::env(TOP_DIR)
load_design 5_top_grt.odb
source $::env(DISSOLVE_NESTED_TCL)

set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set grid [dissolve_nested::grid $block]
lassign $grid x0 y0 sw rh orients x1

set records {}
proc record { key value } {
  lappend ::records "$key $value"
}
proc require { what ok message } {
  if { !$ok } {
    utl::error FLW 148 "dissolve_nested_check: $what: $message"
  }
}

# script, run in the caller, must stop with the message id, its message
# holding each of words
proc must_raise { control id words script } {
  utl::redirectStringBegin
  set rc [catch { uplevel 1 $script } msg]
  set out [utl::redirectStringEnd]
  set line ""
  foreach l [split $out "\n"] {
    if { [string first "$id\]" $l] >= 0 } {
      set line [string trim $l]
    }
  }
  set ok [expr { $rc == 1 && [string first $id $msg] >= 0 && $line ne "" }]
  foreach w $words {
    if { [string first $w $line] < 0 } {
      set ok 0
    }
  }
  if { !$ok } {
    set got [expr { $rc ? "$msg: [string trim $out]" : "it passed" }]
    utl::error FLW 148 "dissolve_nested_check: control $control did not stop with $id\
      for its reason ([join $words {, }]): $got"
  }
  puts "dissolve_nested_check: control $control stopped as it must: $line"
  record control_$control $id
}

# where the containing macro's own global route put master's instance, in
# the Top: {macro orient x y}, the parent at the die's origin, a block at
# its hole
set holes [dict create]
foreach {m x y w h} $::env(HOLES) {
  dict set holes $m [list [expr { int(round($x * $dbu)) }] [expr { int(round($y * $dbu)) }]]
}
proc placed_by { master } {
  foreach m $::env(DISSOLVE_MASTERS) odb $::env(DISSOLVE_ODBS) {
    set db [odb::read_db NULL $odb]
    set found {}
    foreach inst [[[$db getChip] getBlock] getInsts] {
      if { [[$inst getMaster] getName] eq $master } {
        set b [$inst getBBox]
        lappend found [list [$inst getOrient] [$b xMin] [$b yMin]]
      }
    }
    odb::dbDatabase_destroy $db
    if { [llength $found] == 0 } {
      continue
    }
    require $master [expr { [llength $found] == 1 }] "$m holds [llength $found] instances"
    lassign [lindex $found 0] orient x y
    lassign {0 0} ox oy
    if { [dict exists $::holes $m] } {
      lassign [dict get $::holes $m] ox oy
    }
    return [list $m $orient [expr { $x + $ox }] [expr { $y + $oy }]]
  }
  require $master 0 "no macro the Top dissolved holds an instance of it"
}

# each supply net's rails, by layer and row: the special wires no taller
# than a few rows, under every row they touch
set rails [dict create]
foreach net [$block getNets] {
  if { [$net getSigType] ne "POWER" && [$net getSigType] ne "GROUND" } {
    continue
  }
  foreach swire [$net getSWires] {
    foreach box [$swire getWires] {
      if { [$box isVia] || [$box yMax] - [$box yMin] > 4 * $rh } {
        continue
      }
      set layer [[$box getTechLayer] getName]
      set r0 [expr { ([$box yMin] - $y0) / $rh }]
      set r1 [expr { ([$box yMax] - $y0) / $rh }]
      for { set r $r0 } { $r <= $r1 } { incr r } {
        dict lappend rails "[$net getName] $layer $r" \
          [list [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
      }
    }
  }
}
# the layers of a master's pin's shapes
set pin_layers [dict create]
proc pin_layers { mterm } {
  set key "[[$mterm getMaster] getName]/[$mterm getName]"
  if { ![dict exists $::pin_layers $key] } {
    set layers {}
    foreach mpin [$mterm getMPins] {
      foreach box [$mpin getGeometry] {
        if { [$box getTechLayer] ne "NULL" } {
          lappend layers [[$box getTechLayer] getName]
        }
      }
    }
    dict set ::pin_layers $key [lsort -unique $layers]
  }
  return [dict get $::pin_layers $key]
}
# iterm's net has a rail on one of the pin's layers that touches the pin
proc on_rail { iterm } {
  set net [$iterm getNet]
  if { $net eq "NULL" } {
    return 0
  }
  set b [$iterm getBBox]
  set r0 [expr { ([$b yMin] - $::y0) / $::rh }]
  set r1 [expr { ([$b yMax] - $::y0) / $::rh }]
  foreach layer [pin_layers [$iterm getMTerm]] {
    for { set r $r0 } { $r <= $r1 } { incr r } {
      set key "[$net getName] $layer $r"
      if { ![dict exists $::rails $key] } {
        continue
      }
      foreach rail [dict get $::rails $key] {
        lassign $rail rx0 ry0 rx1 ry1
        if { [$b xMin] <= $rx1 && $rx0 <= [$b xMax] && [$b yMin] <= $ry1 && $ry0 <= [$b yMax] } {
          return 1
        }
      }
    }
  }
  return 0
}

# the Top's clock tree cells: every buffer and inverter of the libraries
set tree_masters [dict create]
foreach cell [get_lib_cells *] {
  if { [get_property $cell is_buffer] || [get_property $cell is_inverter] } {
    dict set tree_masters [get_property $cell name] 1
  }
}
# the nets of the Top's ports: no register is on one after the tree
set port_nets {}
foreach bterm [$block getBTerms] {
  if { [$bterm getNet] ne "NULL" && [$bterm getSigType] ne "POWER" && [$bterm getSigType] ne "GROUND" } {
    lappend port_nets [[$bterm getNet] getName]
  }
}
set clocked_pins [dict create]
foreach pin [all_registers -clock [all_clocks] -clock_pins] {
  set iterm [sta::sta_to_db_pin $pin]
  if { $iterm ne "NULL" } {
    dict set clocked_pins [$iterm getName] 1
  }
}
set register_clock_pins [all_registers -clock_pins]

# a cell the strip takes: a TIMING cell of the source whose input is on
# a clock net there (dbInst::dissolve's strip, patch 0171)
proc clock_cell { s } {
  if { [$s getSourceType] ne "TIMING" } {
    return 0
  }
  foreach iterm [$s getITerms] {
    set type [[$iterm getMTerm] getSigType]
    if { $type ne "POWER" && $type ne "GROUND" && [$iterm getIoType] eq "INPUT" } {
      set net [$iterm getNet]
      return [expr { $net ne "NULL" && [$net getSigType] eq "CLOCK" }]
    }
  }
  return 0
}

set masters $::env(DISSOLVE_NESTED_MASTERS)
set odbs $::env(DISSOLVE_NESTED_ODBS)
set clocks $::env(DISSOLVE_NESTED_CLOCKS)
record nested $masters
foreach master $masters odb $odbs {
  set prop [odb::dbStringProperty_find $block "dissolve_nested $master"]
  require $master [expr { $prop ne "NULL" }] "the Top records no dissolve of it"
  lassign [$prop getValue] hier orient x y dx dy
  lassign [placed_by $master] macro p_orient p_x p_y
  require $master [expr { $orient eq $p_orient && $x == $p_x && $y == $p_y }] \
    "dissolved from $orient at $x $y dbu, but $macro placed it $p_orient at $p_x $p_y"
  require $master [expr { abs($dx) < $sw && abs($dy) <= $rh }] \
    "moved $dx $dy dbu onto the rows, more than a site ($sw) or a row ($rh)"
  record $master.placed_by $macro
  record $master.move "$dx $dy"

  # the dissolved module, its cells by name
  set mod_inst "NULL"
  foreach mi [$block getModInsts] {
    if { [$mi getHierarchicalName] eq $hier } {
      set mod_inst $mi
      break
    }
  }
  require $master [expr { $mod_inst ne "NULL" }] "no module instance $hier"
  set module [$mod_inst getMaster]
  set prefix "$hier/"
  set cells [dict create]
  foreach inst [$module getInsts] {
    dict set cells [string range [$inst getName] [string length $prefix] end] $inst
  }

  # every source cell where its flow placed it, through the instance
  set sdb [odb::read_db NULL $odb]
  set src [[$sdb getChip] getBlock]
  set die [$src getDieArea]
  set w [$die dx]
  set h [$die dy]
  set placed 0
  set elsewhere 0
  set stripped 0
  set missing 0
  set src_registers 0
  set sample {}
  foreach s [$src getInsts] {
    if { [[$s getMaster] isSequential] } {
      incr src_registers
    }
    set name [$s getName]
    if { ![dict exists $cells $name] } {
      if { [clock_cell $s] } {
        incr stripped
      } else {
        incr missing
        if { [llength $sample] < 3 } {
          lappend sample "$name missing"
        }
      }
      continue
    }
    set t [dict get $cells $name]
    lassign [dissolve_nested::landed [$s getBBox] $die $orient $x $y $w $h] cx cy
    set b [$t getBBox]
    if { [$b xMin] == $cx + $dx && [$b yMin] == $cy + $dy && [$t getPlacementStatus] eq "LOCKED" } {
      incr placed
    } else {
      incr elsewhere
      if { [llength $sample] < 3 } {
        lappend sample "$name at [$b xMin] [$b yMin] [$t getPlacementStatus], its flow's\
          place [expr { $cx + $dx }] [expr { $cy + $dy }]"
      }
    }
  }
  odb::dbDatabase_destroy $sdb
  record $master.cells [dict size $cells]
  record $master.where_placed $placed
  record $master.elsewhere $elsewhere
  record $master.stripped_clock_cells $stripped
  record $master.missing $missing
  require $master [expr { $placed == [dict size $cells] && $elsewhere == 0 && $missing == 0 }] \
    "$placed of [dict size $cells] cells where its flow placed them, $elsewhere elsewhere,\
    $missing of its database's not dissolved: $sample"

  # on the Top's rows, in their orientation
  set c [dissolve_nested::settle $module $grid {}]
  set off [expr { [dict get $c off_row] + [dict get $c off_site] }]
  record $master.off_grid $off
  record $master.flipped [dict get $c flipped]
  require $master [expr { $off == 0 && [dict get $c flipped] == 0 }] \
    "$off cells off the Top's rows or sites, [dict get $c flipped] in a row of the\
    other orientation: [dict get $c sample]"

  # powered by the Top's grid
  set unpowered 0
  set sample {}
  foreach inst [$module getInsts] {
    foreach iterm [$inst getITerms] {
      set type [[$iterm getMTerm] getSigType]
      if { ($type eq "POWER" || $type eq "GROUND") && ![on_rail $iterm] } {
        incr unpowered
        if { [llength $sample] < 3 } {
          lappend sample [$iterm getName]
        }
      }
    }
  }
  record $master.supply_pins_off_the_grid $unpowered
  require $master [expr { $unpowered == 0 }] \
    "$unpowered supply pins of its cells touch no special wire of their net: $sample"

  # clocked by the Top's tree
  set registers 0
  set clocked 0
  set by_tree 0
  set drivers [dict create]
  set sample {}
  foreach pin $register_clock_pins {
    set iterm [sta::sta_to_db_pin $pin]
    if { $iterm eq "NULL" || [[$iterm getInst] getModule] ne $module } {
      continue
    }
    incr registers
    if { [dict exists $clocked_pins [$iterm getName]] } {
      incr clocked
    }
    set net [$iterm getNet]
    set driver "NULL"
    if { $net ne "NULL" } {
      set driver [$net getFirstOutput]
    }
    if {
      $driver ne "NULL"
      && [dict exists $tree_masters [[[$driver getInst] getMaster] getName]]
      && [[$driver getInst] getSourceType] eq "TIMING"
      && [[$driver getInst] getModule] ne $module
      && [$net getName] ni $port_nets
    } {
      incr by_tree
      dict set drivers [[$driver getInst] getName] 1
    } elseif { [llength $sample] < 3 } {
      lappend sample "[$iterm getName] on [expr { $net eq "NULL" ? "no net" : [$net getName] }]"
    }
  }
  record $master.registers $registers
  record $master.database_registers $src_registers
  record $master.clocked $clocked
  record $master.clocked_by_the_top_tree $by_tree
  record $master.tree_drivers [dict size $drivers]
  require $master [expr { $registers == $src_registers && $registers > 0 }] \
    "$registers registers dissolved, $src_registers in its database"
  require $master [expr { $clocked == $registers && $by_tree == $registers }] \
    "of $registers registers $clocked clocked, $by_tree driven by the Top's clock tree:\
    $sample"
  # a supply net is no clock net: settle counts the registers' clock pins
  # only
  set c [dissolve_nested::settle $module $grid {VSS VDD}]
  require $master [expr { [dict get $c clocked] == 0 }] \
    "[dict get $c clocked] registers counted as clocked on the supply nets"
  puts "dissolve_nested_check: $master ($hier): [dict size $cells] cells where its flow\
    placed them, moved $dx $dy dbu onto the rows, every supply pin on the grid,\
    $registers registers clocked by [dict size $drivers] cells of the Top's tree"
}

# the stops, each on purpose
set master [lindex $masters 0]
set odb [lindex $odbs 0]
lassign [[odb::dbStringProperty_find $block "dissolve_nested $master"] getValue] hier orient x y
set module "NULL"
foreach mi [$block getModInsts] {
  if { [$mi getHierarchicalName] eq $hier } {
    set module [$mi getMaster]
  }
}
set cell "NULL"
foreach inst [$module getInsts] {
  if { ![[$inst getMaster] isBlock] && ![$inst isDoNotTouch] && [$inst getITerms] ne "" } {
    set cell $inst
    break
  }
}
set src_db [odb::read_db NULL $odb]
set src [[$src_db getChip] getBlock]
set die [$src getDieArea]
set src_registers [dissolve_nested::registers $src]
set macro [[ord::get_db] findMaster $master]
# a probe named name, unconnected, at the place master's parent gave it,
# in orientation o; moved onto the rows by dissolve_nested.tcl's move when
# move is set. Returns it and the move.
proc probe { name o move } {
  set inst [odb::dbInst_create $::block $::macro $name]
  $inst setOrient $o
  $inst setLocation $::x $::y
  $inst setPlacementStatus PLACED
  lassign {0 0} dx dy
  if { $move } {
    lassign [dissolve_nested::move $inst $::src $::grid] dx dy
    $inst setLocation [expr { $::x + $dx }] [expr { $::y + $dy }]
  }
  return [list $inst $dx $dy]
}

must_raise absent FLW-0141 {NoSuchMacro {0 instances}} {
  dissolve_nested::run $block {NoSuchMacro} [list $odb] $clocks {}
}
set other [lindex $::env(DISSOLVE_ODBS) 0]
must_raise odb FLW-0140 [list $master {not}] {
  dissolve_nested::check_odb $master $other
}
# the dissolve of a probe with none of its pins on a net, the only
# instance of its master now that the first pass dissolved it
set inst [lindex [probe dissolve_nested_probe_no_clock $orient 0] 0]
must_raise no_clock FLW-0142 [list $master {none of the clock pins}] {
  dissolve_nested::run $block [list $master] [list $odb] $clocks {}
}
odb::dbInst_destroy $inst

set b [$cell getBBox]
set cell_x [$b xMin]
set cell_y [$b yMin]
set cell_orient [$cell getOrient]
proc put_back { } {
  $::cell setPlacementStatus PLACED
  $::cell setOrient $::cell_orient
  $::cell setLocation $::cell_x $::cell_y
  $::cell setPlacementStatus LOCKED
}
$cell setPlacementStatus PLACED
$cell setLocation $cell_x [expr { $cell_y + 1 }]
must_raise off_row FLW-0144 [list $master {1 off the rows}] {
  dissolve_nested::stop_on $master [dissolve_nested::settle $module $grid {}] 0 {}
}
put_back
set turned [expr { [dissolve_nested::side $cell_orient] eq "N" ? "MX" : "R0" }]
$cell setPlacementStatus PLACED
$cell setLocationOrient $turned
must_raise flipped FLW-0144 [list $master {1 in a row of the other orientation}] {
  dissolve_nested::stop_on $master [dissolve_nested::settle $module $grid {}] 0 {}
}
put_back

# a probe dissolved onto the rows, one of its registers unplaced and then
# gone, against its database's registers
set inst [lindex [probe dissolve_nested_probe_fewer $orient 1] 0]
set mod [[dissolve_macro -inst dissolve_nested_probe_fewer -db $odb] getMaster]
set n [llength [$mod getInsts]]
set register "NULL"
foreach inst [$mod getInsts] {
  if { [[$inst getMaster] isSequential] } {
    set register $inst
    break
  }
}
$register setPlacementStatus NONE
must_raise unplaced FLW-0143 [list $master "1 of $n dissolved cells are not placed" [$register getName]] {
  dissolve_nested::stop_on $master [dissolve_nested::settle $mod $grid {}] $src_registers {}
}
odb::dbInst_destroy $register
must_raise fewer FLW-0145 [list $master "[expr { $src_registers - 1 }] registers dissolved, $src_registers in its database"] {
  dissolve_nested::stop_on $master [dissolve_nested::settle $mod $grid {}] $src_registers {}
}

# a probe with its clock pins on a net, dissolved with its own clock tree
# kept: its registers hang off that tree's buffers, not the net
set inst [lindex [probe dissolve_nested_probe_unclocked $orient 0] 0]
set net [odb::dbNet_create $block dissolve_nested_probe_clock]
foreach pin $clocks {
  set iterm [$inst findITerm $pin]
  if { $iterm ne "NULL" } {
    $iterm connect $net
  }
}
must_raise unclocked FLW-0146 [list $master dissolve_nested_probe_clock {clock buffer or gate}] {
  dissolve_nested::run $block [list $master] [list $odb] $clocks {}
}

set supply "NULL"
foreach iterm [$cell getITerms] {
  set type [[$iterm getMTerm] getSigType]
  if { $type eq "POWER" || $type eq "GROUND" } {
    set supply $iterm
    break
  }
}
set supply_net [$supply getNet]
$supply disconnect
must_raise supply FLW-0147 [list {1 supply pins} [$supply getName]] {
  dissolve_nested::check_supply [list $module]
}
$supply connect $supply_net

foreach o {MX MY R180} {
  set name "dissolve_nested_probe_$o"
  lassign [probe $name $o 1] inst dx dy
  set mod [[dissolve_macro -inst $name -db $odb] getMaster]
  set c [dissolve_nested::settle $mod $grid {}]
  set placed 0
  set sample {}
  foreach s [$src getInsts] {
    set t [$block findInst "$name/[$s getName]"]
    lassign [dissolve_nested::landed [$s getBBox] $die $o $x $y [$die dx] [$die dy]] cx cy
    if { $t ne "NULL" && [[$t getBBox] xMin] == $cx + $dx && [[$t getBBox] yMin] == $cy + $dy } {
      incr placed
    } elseif { [llength $sample] < 3 } {
      lappend sample [$s getName]
    }
  }
  set off [expr { [dict get $c off_row] + [dict get $c off_site] }]
  record probe_$o.cells [dict get $c cells]
  record probe_$o.where_placed $placed
  record probe_$o.off_grid $off
  record probe_$o.flipped [dict get $c flipped]
  record probe_$o.move "$dx $dy"
  require "$master $o" [expr { $placed == [dict get $c cells] && [dict get $c cells] > 0 }] \
    "$placed of [dict get $c cells] cells where its flow placed them: $sample"
  require "$master $o" [expr { $off == 0 && [dict get $c flipped] == 0 && abs($dx) < $sw && abs($dy) <= $rh }] \
    "moved $dx $dy dbu, $off cells off the rows or sites, [dict get $c flipped] in a\
    row of the other orientation: [dict get $c sample]"
  puts "dissolve_nested_check: $master $o: [dict get $c cells] cells where its flow placed\
    them, moved $dx $dy dbu onto the rows in their orientation"
}
odb::dbDatabase_destroy $src_db

set f [open $::env(NESTED_TXT) w]
puts $f [join $::records "\n"]
close $f
puts "dissolve_nested_check: [llength $masters] nested macros checked, every control stopped"
