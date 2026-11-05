# crossing_cones' flatten mode on a parent macro's top level, its macros
# dissolved (parent_macro.bzl, <pm>_top_flatten_test): what the Top may
# move is the boundary logic, each part's in2reg, reg2out and in2out up to
# the first register, and nothing else.
#
# Stops on the first broken rule:
#   - some cells are movable, and some combinational cells stay fixed: the
#     macros' register-to-register logic is not flattened with the rest;
#   - a movable cell is combinational logic: no register, latch, clock
#     gate, memory, macro or clock network cell moves;
#   - a movable cell is placed, not fixed, not dont_touch; every other cell
#     is fixed and dont_touch;
#   - a movable cell's nets lost their guides and wires (some had guides);
#   - no register's clock net is dont_touch, so the Top's clock tree can
#     be built.
#
# Writes the counts to FLATTEN_TXT.
#
#   CONE_MACROS  the macros whose crossings are flattened ("all")
#   PARENT_INST  the parent's instance (u_parent)
#   FLATTEN_TXT  the counts
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

set block [ord::get_db_block]
set parent [env_var_or_empty PARENT_INST]
if { $parent eq "" } {
  set parent u_parent
}
set guided 0
foreach net [$block getNets] {
  if { [llength [$net getGuides]] > 0 } {
    incr guided
  }
}

set needs [lassign [sta::crossing_cones $::env(CONE_MACROS) $parent 1 0 "" 1] \
  seeds kept before]
set at [lsearch -exact $needs flatten]
if { $at < 0 } {
  utl::error FLW 120 "top_flatten_check: crossing_cones returned no flatten counts: $needs"
}
lassign [lrange $needs [expr { $at + 1 }] end] movable nets
puts "top_flatten_check: $seeds crossing nets, $movable of $before cells movable,\
  $nets nets unrouted, $guided nets had guides"

proc flatten_fail { msg } {
  utl::error FLW 121 "top_flatten_check: $msg"
}
if { $movable == 0 } {
  flatten_fail "no cell is movable"
}

set fixed_logic 0
set n_movable 0
set registers 0
foreach inst [$block getInsts] {
  # a stop as crossing_cones has it: a macro, a cell without liberty, a
  # memory, or a cell with a clock pin (register, latch, clock gate)
  set master [$inst getMaster]
  set mname [$master getName]
  if { ![info exists stops($mname)] } {
    set lib [lindex [get_lib_cells -quiet $mname] 0]
    set stop [expr { [$master isBlock] || $lib eq "" }]
    if { !$stop && [get_property $lib is_memory] } {
      set stop 1
    }
    if { !$stop } {
      foreach pin [get_lib_pins -quiet -of_objects $lib] {
        if { [get_property $pin is_clock] } {
          set stop 1
          break
        }
      }
    }
    set stops($mname) $stop
  }
  set seq $stops($mname)
  set fixed [$inst isFixed]
  set dnt [$inst isDoNotTouch]
  if { !$fixed } {
    incr n_movable
    if { $seq } {
      flatten_fail "[$inst getName] ([[$inst getMaster] getName]) is not\
        combinational and moves"
    }
    if { $dnt } {
      flatten_fail "[$inst getName] moves and is dont_touch"
    }
    foreach iterm [$inst getITerms] {
      set net [$iterm getNet]
      if { $net eq "NULL" || [$net getSigType] in {POWER GROUND} } {
        continue
      }
      if { [llength [$net getGuides]] > 0 || [$net getWire] ne "NULL" } {
        flatten_fail "[$net getName], on movable [$inst getName], kept its route"
      }
      if { [$iterm getSigType] eq "CLOCK" } {
        flatten_fail "[$inst getName] moves and has a clock pin"
      }
    }
    continue
  }
  if { !$dnt } {
    flatten_fail "[$inst getName] is fixed and not dont_touch"
  }
  if { $seq } {
    incr registers
    foreach iterm [$inst getITerms] {
      set net [$iterm getNet]
      if { [$iterm getSigType] eq "CLOCK" && $net ne "NULL" && [$net isDoNotTouch] } {
        flatten_fail "[$net getName], the clock of [$inst getName], is dont_touch"
      }
    }
  } else {
    incr fixed_logic
  }
}
if { $n_movable != $movable } {
  flatten_fail "$n_movable cells are not fixed, crossing_cones made $movable movable"
}
if { $fixed_logic == 0 } {
  flatten_fail "no combinational cell stays fixed: the macros' own logic was flattened"
}
if { $guided == 0 } {
  flatten_fail "no net had guides: nothing was routed to drop"
}

set f [open $::env(FLATTEN_TXT) w]
puts $f "crossing_nets $seeds"
puts $f "movable $movable"
puts $f "unrouted_nets $nets"
puts $f "fixed_logic $fixed_logic"
puts $f "fixed_stops $registers"
close $f
