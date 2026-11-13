# The macros nested in the parent macro or in a block (parent_macro.bzl's
# dissolve_nested: XSTile's generated register files), dissolved at the
# top level after the parent and the blocks (top_dissolve.tcl): each the
# one instance of its master, replaced by the cells of its own flow's
# global route (its 5_1_grt.odb) through the instance's place and
# orientation (dissolve_macro, carried OpenROAD patch 0171), its own clock
# tree left behind so that its registers sit on the net its clock pin was
# on, the Top's clock, for the Top's one tree. Every cell is LOCKED where
# it lands.
#
# The macro's own flow placed its cells on its own rows, and the parent or
# block placed the macro where its plan or macro placer put it, which is
# off the Top's row grid: all nine of XSTile's register files were off its
# rows, and eight of them off its sites too. The instance is first moved
# by the smallest step that puts every one of its cells on the Top's
# rows, each in a row of its own orientation: less than a site across, at
# most a row up or down. On the rows the Top's power grid (pdn.tcl, after
# this step) lays its followpins along the cells' supply pins, as it does
# along the blocks' cells, and the legaliser and check_placement take them
# as they take any fixed cell. A moved macro's pins' nets lose their
# guides, the parent's half of each no longer meeting the macro's, and the
# Top's global route routes them (-unguided_only); a net on its pins that
# the dissolve removed must have been joined by a feedthrough to another
# net on them, whose guides go. The move is a fact of the database: a
# block property "dissolve_nested <master>", the module instance, the
# orientation, the place its parent gave it and the move, in dbu.
#
# Stops where the problem is made, before the cells reach a later step:
#   FLW 140  a master listed twice, a master without its database or a
#            database without its master, a database that is not the
#            master's own flow's or that cannot be read
#   FLW 141  a master with no instance, or several
#   FLW 142  an instance with none of the clock pins on a net
#   FLW 143  a dissolved cell that is not placed
#   FLW 144  a dissolved cell off the Top's rows or sites, where the Top
#            has no row, or in a row of the other orientation; no row of
#            the cells' orientation within a row of the macro
#   FLW 145  fewer registers dissolved than its database holds
#   FLW 146  a register whose clock pin is not on the clock pins' nets: a
#            clock buffer or gate was kept, and CTS would leave its
#            subtree as built
#   FLW 147  a dissolved cell with a supply pin on no net after the global
#            connections (check_supply, after global_connect)
#   FLW 149  dissolve_macro returned no module instance
#   FLW 150  a net on a moved macro's pins gone after the dissolve, not
#            joined by a feedthrough to another net on its pins: its
#            guides would be where nothing clears them
namespace eval dissolve_nested {

# The rows a cell orientation sits in: N for R0 and MY, F for MX and R180.
proc side { orient } {
  if { $orient eq "R0" || $orient eq "MY" } {
    return N
  }
  if { $orient eq "MX" || $orient eq "R180" } {
    return F
  }
  return $orient
}

# The Top's row grid: the rows' x origin, the lowest row's bottom, the
# site's width and height, each row's bottom to its orientation, and the
# rows' right end.
proc grid { block } {
  set orients [dict create]
  set x0 ""
  foreach row [$block getRows] {
    set box [$row getBBox]
    if { $x0 eq "" } {
      set x0 [$box xMin]
      set x1 [$box xMax]
      set site [$row getSite]
      set sw [$site getWidth]
      set rh [$site getHeight]
    }
    set x1 [expr { max($x1, [$box xMax]) }]
    dict set orients [$box yMin] [$row getOrient]
  }
  if { $x0 eq "" } {
    utl::error FLW 144 "dissolve_nested: the top level has no rows to put a macro's cells on"
  }
  set y0 [lindex [lsort -integer [dict keys $orients]] 0]
  return [list $x0 $y0 $sw $rh $orients $x1]
}

# The masters and their databases, in the same order, each once.
proc check_lists { masters odbs } {
  if { [llength $masters] != [llength $odbs] } {
    utl::error FLW 140 "dissolve_nested: [llength $masters] masters ($masters),\
      [llength $odbs] databases"
  }
  if { [llength [lsort -unique $masters]] != [llength $masters] } {
    utl::error FLW 140 "dissolve_nested: a master listed twice: $masters"
  }
}

# odb is the global route of master's own flow: its results are under its
# design's name.
proc check_odb { master odb } {
  if { ![string match "*/$master/*" $odb] } {
    utl::error FLW 140 "dissolve_nested: $odb is not $master's own flow's database"
  }
  if { ![file readable $odb] } {
    utl::error FLW 140 "dissolve_nested: cannot read $master's database $odb"
  }
}

# The instances of each of masters in block, in one pass over its
# instances: a dict of master to its instances.
proc instances { block masters } {
  set found [dict create]
  foreach master $masters {
    dict set found $master {}
  }
  foreach inst [$block getInsts] {
    set master [[$inst getMaster] getName]
    if { [dict exists $found $master] } {
      dict lappend found $master $inst
    }
  }
  return $found
}

# The one instance of master, of found (instances).
proc only { found master } {
  set insts [dict get $found $master]
  if { [llength $insts] != 1 } {
    utl::error FLW 141 "dissolve_nested: $master has [llength $insts] instances,\
      one expected: it is not inside the parent or a block, or a block holds\
      several"
  }
  return [lindex $insts 0]
}

# The registers of block.
proc registers { block } {
  set n 0
  foreach inst [$block getInsts] {
    if { [[$inst getMaster] isSequential] } {
      incr n
    }
  }
  return $n
}

# A master's clock pins, by name: liberty's, and the LEF's USE CLOCK.
variable clock_pins
array set clock_pins {}
proc clock_pins { master } {
  variable clock_pins
  set name [$master getName]
  if { ![info exists clock_pins($name)] } {
    set pins {}
    set lib [lindex [get_lib_cells -quiet $name] 0]
    if { $lib ne "" } {
      foreach pin [get_lib_pins -quiet -of_objects $lib] {
        if { [get_property $pin is_clock] } {
          lappend pins [get_property $pin name]
        }
      }
    }
    foreach mterm [$master getMTerms] {
      if { [$mterm getSigType] eq "CLOCK" && [$mterm getName] ni $pins } {
        lappend pins [$mterm getName]
      }
    }
    set clock_pins($name) $pins
  }
  return $clock_pins($name)
}

# The source's feedthroughs: the names of the ports that share a net, a
# list for each such net. dbInst::dissolve joins the parent's nets on
# them into one.
proc joins { src } {
  set by_net [dict create]
  foreach bterm [$src getBTerms] {
    set net [$bterm getNet]
    set type [$bterm getSigType]
    if { $net ne "NULL" && $type ne "POWER" && $type ne "GROUND" } {
      dict lappend by_net [$net getName] [$bterm getName]
    }
  }
  set joins {}
  dict for {net ports} $by_net {
    if { [llength $ports] > 1 } {
      lappend joins $ports
    }
  }
  return $joins
}

# The names of the nets inst's clock pins (clocks, by name) are on.
proc clock_nets { inst clocks } {
  set nets {}
  foreach pin $clocks {
    set iterm [$inst findITerm $pin]
    if { $iterm ne "NULL" && [$iterm getNet] ne "NULL" } {
      lappend nets [[$iterm getNet] getName]
    }
  }
  if { [llength $nets] == 0 } {
    utl::error FLW 142 "dissolve_nested: [$inst getName] ([[$inst getMaster] getName])\
      has none of the clock pins $clocks on a net"
  }
  return [lsort -unique $nets]
}

# Where a cell at bbox cb of the source block, whose die is die, lands in a
# macro of orientation orient whose box is at x, y and w by h: the source
# die's corner at the box's, mirrored as the instance is (dbInst::dissolve,
# patch 0171). The cell's lower left, in the Top's dbu.
proc landed { cb die orient x y w h } {
  set u0 [expr { [$cb xMin] - [$die xMin] }]
  set u1 [expr { [$cb xMax] - [$die xMin] }]
  set v0 [expr { [$cb yMin] - [$die yMin] }]
  set v1 [expr { [$cb yMax] - [$die yMin] }]
  if { $orient eq "MY" || $orient eq "R180" } {
    set cx [expr { $x + $w - $u1 }]
  } else {
    set cx [expr { $x + $u0 }]
  }
  if { $orient eq "MX" || $orient eq "R180" } {
    set cy [expr { $y + $h - $v1 }]
  } else {
    set cy [expr { $y + $v0 }]
  }
  return [list $cx $cy]
}

# A cell's row side once dissolved into a macro of orientation orient: a
# mirror about the x axis turns a row over.
proc landed_side { orient cell_orient } {
  set s [side $cell_orient]
  if { $orient eq "MX" || $orient eq "R180" } {
    return [expr { $s eq "N" ? "F" : ($s eq "F" ? "N" : $s) }]
  }
  return $s
}

# The move, {dx dy} in dbu, that puts the cells inst dissolves into from
# the source block src on the Top's rows (grid) in their orientation, read
# from one placed one-row cell of the source: the source's cells are all on
# its own rows, so one move fits them all. Less than a site across, at
# most a row up or down; FLW 144 when no row of that orientation is that
# near. Rows alternate, so of the two nearest one is of that orientation
# unless the other is the core's last.
proc move { inst src grid } {
  lassign $grid x0 y0 sw rh orients
  set bb [$inst getBBox]
  set orient [$inst getOrient]
  set die [$src getDieArea]
  set ref "NULL"
  foreach cell [$src getInsts] {
    set m [$cell getMaster]
    if { [$cell isPlaced] && ![$m isBlock] && [$m getHeight] == $rh } {
      set ref $cell
      break
    }
  }
  if { $ref eq "NULL" } {
    # nothing in rows to put on them
    return {0 0}
  }
  lassign [landed [$ref getBBox] $die $orient [$bb xMin] [$bb yMin] [$bb getDX] [$bb getDY]] cx cy
  set s [landed_side $orient [$ref getOrient]]
  set rx [expr { ($cx - $x0) % $sw }]
  set dx [expr { 2 * $rx <= $sw ? -$rx : $sw - $rx }]
  set ry [expr { ($cy - $y0) % $rh }]
  set d0 [expr { 2 * $ry <= $rh ? -$ry : $rh - $ry }]
  foreach dy [lsort -command ::dissolve_nested::by_size [list $d0 [expr { $d0 - $rh }] [expr { $d0 + $rh }]]] {
    set row [expr { $cy + $dy }]
    if { abs($dy) <= $rh && [dict exists $orients $row]
         && [side [dict get $orients $row]] eq $s } {
      return [list $dx $dy]
    }
  }
  utl::error FLW 144 "dissolve_nested: [$inst getName] ([[$inst getMaster] getName]):\
    no row of the Top's in its cells' orientation within a row of where its\
    parent placed it ([$bb xMin] [$bb yMin] dbu, $orient)"
}

proc by_size { a b } {
  if { abs($a) != abs($b) } {
    return [expr { abs($a) < abs($b) ? -1 : 1 }]
  }
  return [expr { $a < $b ? -1 : ($a > $b ? 1 : 0) }]
}

# Every cell of module LOCKED where it is, and counted against the Top's
# grid and clock: a dict of cells, unplaced, off_row (off the rows' lattice
# or where the Top has no row), off_site, flipped (in a row of the other
# orientation), registers, clocked (registers with a clock pin on one of
# the nets named clock_nets) and a few offenders' names, a register's
# among them only when clock_nets names a net.
proc settle { module grid clock_nets } {
  lassign $grid x0 y0 sw rh orients x1
  set on [dict create]
  foreach n $clock_nets {
    dict set on $n 1
  }
  set c [dict create cells 0 unplaced 0 off_row 0 off_site 0 flipped 0 \
    registers 0 clocked 0 sample {}]
  foreach inst [$module getInsts] {
    dict incr c cells
    if { ![$inst isPlaced] } {
      dict incr c unplaced
      if { [llength [dict get $c sample]] < 3 } {
        dict lappend c sample "[$inst getName] (unplaced)"
      }
      continue
    }
    $inst setPlacementStatus LOCKED
    set m [$inst getMaster]
    if { ![$m isBlock] } {
      set b [$inst getBBox]
      set cx [$b xMin]
      set cy [$b yMin]
      set bad ""
      if { ($cy - $y0) % $rh != 0 || ![dict exists $orients $cy]
           || $cx < $x0 || [$b xMax] > $x1 } {
        dict incr c off_row
        set bad "off the rows"
      } elseif { [side [dict get $orients $cy]] ne [side [$inst getOrient]] } {
        dict incr c flipped
        set bad "[$inst getOrient] in a [dict get $orients $cy] row"
      }
      if { ($cx - $x0) % $sw != 0 } {
        dict incr c off_site
        set bad "off the sites"
      }
      if { $bad ne "" && [llength [dict get $c sample]] < 3 } {
        dict lappend c sample "[$inst getName] at $cx $cy ($bad)"
      }
    }
    if { [$m isSequential] } {
      dict incr c registers
      set on_clock 0
      foreach pin [clock_pins $m] {
        set iterm [$inst findITerm $pin]
        if { $iterm ne "NULL" && [$iterm getNet] ne "NULL"
             && [dict exists $on [[$iterm getNet] getName]] } {
          set on_clock 1
          break
        }
      }
      if { $on_clock } {
        dict incr c clocked
      } elseif { [llength $clock_nets] > 0 && [llength [dict get $c sample]] < 3 } {
        dict lappend c sample "[$inst getName] (clock pins [clock_pins $m] off $clock_nets)"
      }
    }
  }
  return $c
}

# The stops on a dissolved macro's counts (settle): src_registers is its
# database's register count.
proc stop_on { master c src_registers clock_nets } {
  set sample [dict get $c sample]
  if { [dict get $c unplaced] > 0 } {
    utl::error FLW 143 "dissolve_nested: $master: [dict get $c unplaced] of\
      [dict get $c cells] dissolved cells are not placed: $sample"
  }
  set off [expr { [dict get $c off_row] + [dict get $c off_site] + [dict get $c flipped] }]
  if { $off > 0 } {
    utl::error FLW 144 "dissolve_nested: $master: $off of [dict get $c cells] cells\
      not on the Top's rows in their orientation: [dict get $c off_row] off the\
      rows, [dict get $c off_site] off the sites, [dict get $c flipped] in a row\
      of the other orientation: $sample"
  }
  if { [dict get $c registers] < $src_registers } {
    utl::error FLW 145 "dissolve_nested: $master: [dict get $c registers] registers\
      dissolved, $src_registers in its database"
  }
  if { [dict get $c clocked] < [dict get $c registers] } {
    utl::error FLW 146 "dissolve_nested: $master: [dict get $c clocked] of\
      [dict get $c registers] registers with a clock pin on its clock pins'\
      nets ($clock_nets): a clock buffer or gate of its own was kept, and CTS\
      would leave that subtree as built: $sample"
  }
}

# The parent's half of each net on a moved macro's pins ends where the
# pin was: its guides go, for the Top's global route. ports is the pins'
# nets before the dissolve, pin name to net name, joins the source's
# feedthroughs (joins). A net the dissolve removed was joined to another
# of a feedthrough's nets, which carries its guides now and loses them
# here; any other stops (FLW 150). Returns how many nets lost guides.
proc unguide { block master ports joins } {
  set unguided 0
  set gone {}
  foreach n [lsort -unique [dict values $ports]] {
    set net [$block findNet $n]
    if { $net eq "NULL" } {
      lappend gone $n
    } elseif { [llength [$net getGuides]] > 0 } {
      $net clearGuides
      incr unguided
    }
  }
  set lost {}
  foreach n $gone {
    set kept 0
    foreach pins $joins {
      set group {}
      foreach pin $pins {
        if { [dict exists $ports $pin] } {
          lappend group [dict get $ports $pin]
        }
      }
      if { $n in $group } {
        foreach other $group {
          if { $other ni $gone } {
            set kept 1
          }
        }
      }
    }
    if { !$kept } {
      lappend lost $n
    }
  }
  if { [llength $lost] > 0 } {
    utl::error FLW 150 "dissolve_nested: $master: [llength $lost] nets on its pins\
      gone after the dissolve, not joined by a feedthrough to another net on\
      its pins, their guides where nothing clears them: [lrange $lost 0 2]"
  }
  return $unguided
}

# Dissolve each of masters from its database (odbs, in order) in block,
# after the parent and the blocks; clocks are the macros' clock pins by
# name, buffers the masters dissolve_macro strips. The rows are the
# Top's. Returns the dissolved modules.
proc run { block masters odbs clocks buffers } {
  check_lists $masters $odbs
  set grid [grid $block]
  set found [instances $block $masters]
  set modules {}
  foreach master $masters odb $odbs {
    set inst [only $found $master]
    check_odb $master $odb
    set name [$inst getName]
    set nets [clock_nets $inst $clocks]

    # the source: its registers, its feedthroughs, and the move onto the
    # Top's rows
    set sdb [odb::read_db NULL $odb]
    if { $sdb eq "NULL" } {
      utl::error FLW 140 "dissolve_nested: cannot read $master's database $odb"
    }
    set src [[$sdb getChip] getBlock]
    set src_registers [registers $src]
    set joins [joins $src]
    lassign [move $inst $src $grid] dx dy
    odb::dbDatabase_destroy $sdb

    set bb [$inst getBBox]
    set x [$bb xMin]
    set y [$bb yMin]
    set orient [$inst getOrient]
    set ports [dict create]
    if { $dx != 0 || $dy != 0 } {
      foreach iterm [$inst getITerms] {
        set net [$iterm getNet]
        if { $net ne "NULL" && [$net getSigType] ne "POWER" && [$net getSigType] ne "GROUND" } {
          dict set ports [[$iterm getMTerm] getName] [$net getName]
        }
      }
      set status [$inst getPlacementStatus]
      $inst setPlacementStatus PLACED
      $inst setLocation [expr { $x + $dx }] [expr { $y + $dy }]
      $inst setPlacementStatus $status
    }

    set mod_inst [dissolve_macro -inst $name -db $odb -strip_clock_buffers $buffers]
    if { $mod_inst eq "" || $mod_inst eq "NULL" } {
      utl::error FLW 149 "dissolve_nested: dissolve_macro returned no module instance for $name"
    }
    set module [$mod_inst getMaster]
    set c [settle $module $grid $nets]
    stop_on $master $c $src_registers $nets
    set unguided [unguide $block $master $ports $joins]
    set hier [$mod_inst getHierarchicalName]
    odb::dbStringProperty_create $block "dissolve_nested $master" \
      [list $hier $orient $x $y $dx $dy]
    puts "dissolve_nested: $master ($name, $orient at $x $y dbu) from $odb:\
      [dict get $c cells] cells LOCKED where its flow placed them, moved $dx $dy dbu\
      onto the Top's rows; [dict get $c registers] registers (its database\
      $src_registers), all on $nets; $unguided nets on its pins left to the\
      Top's global route"
    lappend modules $module
  }
  return $modules
}

# Every supply pin of the cells of modules on a net, after the global
# connections.
proc check_supply { modules } {
  set open 0
  set sample {}
  foreach module $modules {
    foreach inst [$module getInsts] {
      foreach iterm [$inst getITerms] {
        set type [[$iterm getMTerm] getSigType]
        if { ($type eq "POWER" || $type eq "GROUND") && [$iterm getNet] eq "NULL" } {
          incr open
          if { [llength $sample] < 3 } {
            lappend sample [$iterm getName]
          }
        }
      }
    }
  }
  if { $open > 0 } {
    utl::error FLW 147 "dissolve_nested: $open supply pins of the dissolved macros'\
      cells on no net after the global connections: $sample"
  }
}

}
