# The parent's crossings for the global floorplan planner, from its
# hierarchical synthesis (OPENROAD_HIERARCHICAL=1, the blocks kept
# modules), as a tab-separated dump parent_json.py turns into parent.json:
#
#   parent <top module>
#   glue   <um2>                   the parent's own cells
#   module <instance> <module> <um2>  each kept block under the top
#   cross  <from> <from inst> <from bit> <to> <to inst> <to bit> <via> <depth> <t0> <t1>
#
# A crossing is one port bit of a block (or of the top) reaching a port
# bit of another through the parent's wires, combinational cells and at
# most one register (via wire, comb or reg), every bit of every boundary
# counted. <from>/<to> is a block's module (its instance beside it) or
# the top's (instance "-"). t0 and t1 are the
# arrivals at the net leaving <from> and at the net entering <to>, every
# input at 0, no wire (through a register t0 is 0, the register's
# launch): the parent's own delay between the boundaries is t1 - t0 over
# the bus, parent_json.py's.
#
#   EXTRACT_OUT    the dump
#   EXTRACT_DEPTH  parent cells a crossing is followed through (64)
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb

set out [open $::env(EXTRACT_OUT) w]
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set top [$block getTopModule]
set top_name [$top getName]
set depth_max [expr { [info exists ::env(EXTRACT_DEPTH)] ? $::env(EXTRACT_DEPTH) : 64 }]
puts $out "parent\t$top_name"

proc module_name { mi } {
  # a uniquified module is <module>$<parent>.<instance>
  return [lindex [split [[$mi getMaster] getName] "\$"] 0]
}

# each instance's area to the kept block under the top it sits in
proc top_child { inst } {
  set mi [[$inst getModule] getModInst]
  set last ""
  while { $mi ne "NULL" } {
    set last $mi
    set mi [[$mi getParent] getModInst]
  }
  return $last
}
set area [dict create]
set glue 0.0
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set a [expr { double([$m getWidth]) * [$m getHeight] / $dbu / $dbu }]
  if { [$inst getModule] eq $top } {
    set glue [expr { $glue + $a }]
  } else {
    set c [top_child $inst]
    if { $c ne "" } {
      set k [$c getName]
      dict set area $k [expr { ([dict exists $area $k] ? [dict get $area $k] : 0.0) + $a }]
    }
  }
}
puts $out "glue\t[format %.3f $glue]"
foreach mi [$top getChildren] {
  set k [$mi getName]
  set a [expr { [dict exists $area $k] ? [dict get $area $k] : 0.0 }]
  puts $out "module\t$k\t[module_name $mi]\t[format %.3f $a]"
}

set sequential [dict create]
foreach reg [all_registers -cells] {
  dict set sequential [get_property $reg ref_name] 1
}

# arrivals: every input at 0 on the first clock
set ui_ps [expr { [sta::time_ui_sta 1.0] * 1e12 }]
set clk [lindex [all_clocks] 0]
set clock_ports [get_full_name [get_property $clk sources]]
set inputs [all_inputs -no_clocks]
if { [llength $inputs] > 0 } { set_input_delay 0 -clock $clk $inputs }
proc net_arrival { net } {
  if { $net eq "NULL" } { return 0.0 }
  set best 0.0
  set n [sta::db_net_to_sta $net]
  if { $n eq "NULL" || $n eq "" } { return 0.0 }
  foreach p [get_pins -quiet -of_objects $n] {
    if { [get_property $p direction] ne "output" } { continue }
    foreach rf {arrival_max_rise arrival_max_fall} {
      set a [get_property $p $rf]
      if { [string is double -strict $a] && abs($a) < 1e20 } {
        set best [expr { max($best, $a * $::ui_ps) }]
      }
    }
  }
  return $best
}

proc emit { from from_bit to to_bit via depth t0 t1 } {
  lassign $from fm fi
  lassign $to tm ti
  puts $::out "cross\t$fm\t$fi\t$from_bit\t$tm\t$ti\t$to_bit\t$via\t$depth\t[format %.1f $t0]\t[format %.1f $t1]"
}

# Forward from one boundary bit through the parent: the bits it reaches.
# A step is a modnet (a net with a boundary on it) or a flat net (the
# parent's own); a parent cell's outputs are the next steps.
proc follow { from from_bit start_modnet start_net } {
  set t0 [net_arrival $start_net]
  set todo [list [list $start_modnet $start_net 0 0]]
  set seen [dict create]
  while { [llength $todo] > 0 } {
    set next {}
    foreach item $todo {
      lassign $item modnet net depth regs
      set key "[expr { $modnet eq "NULL" ? "n[$net getId]" : "m[$modnet getId]" }]/$regs"
      if { [dict exists $seen $key] } { continue }
      dict set seen $key 1
      set via [expr { $regs ? "reg" : ($depth > 0 ? "comb" : "wire") }]
      set flat [expr { $modnet ne "NULL" ? [$modnet findRelatedNet] : $net }]
      set t1 [expr { $depth > 0 ? [net_arrival $flat] : $t0 }]
      set s0 [expr { $regs ? 0.0 : $t0 }]
      set iterms {}
      set bterms {}
      if { $modnet ne "NULL" } {
        foreach o [$modnet getModITerms] {
          if { [[$o getChildModBTerm] getIoType] ne "INPUT" } { continue }
          set mi [$o getParent]
          emit $from $from_bit [list [module_name $mi] [$mi getName]] [$o getName] $via $depth $s0 $t1
        }
        set bterms [$modnet getBTerms]
        set iterms [$modnet getITerms]
      } elseif { $net ne "NULL" } {
        set bterms [$net getBTerms]
        set iterms [$net getITerms]
      }
      foreach bt $bterms {
        if { [$bt getIoType] eq "OUTPUT" } {
          emit $from $from_bit [list $::top_name -] [$bt getName] $via $depth $s0 $t1
        }
      }
      if { $depth >= $::depth_max } { continue }
      foreach it $iterms {
        set inst [$it getInst]
        if { [$inst getModule] ne $::top || ![$it isInputSignal] } { continue }
        set r $regs
        if { [dict exists $::sequential [[$inst getMaster] getName]] } {
          if { $regs } { continue }
          set r 1
        }
        foreach o [$inst getITerms] {
          if { [$o isOutputSignal] } {
            lappend next [list [$o getModNet] [$o getNet] [expr { $depth + 1 }] $r]
          }
        }
      }
    }
    set todo $next
  }
}

foreach mi [$top getChildren] {
  set from [list [module_name $mi] [$mi getName]]
  foreach t [$mi getModITerms] {
    if { [[$t getChildModBTerm] getIoType] ne "OUTPUT" } { continue }
    set n [$t getModNet]
    if { $n eq "NULL" } { continue }
    follow $from [$t getName] $n [$n findRelatedNet]
  }
}
foreach bt [$block getBTerms] {
  if { [$bt getIoType] ne "INPUT" || [$bt getSigType] ne "SIGNAL" } { continue }
  if { [lsearch -exact $clock_ports [$bt getName]] >= 0 } { continue }
  follow [list $top_name -] [$bt getName] [$bt getModNet] [$bt getNet]
}
close $out
puts "extract_parent: $top_name written to $::env(EXTRACT_OUT)"
