# The parent's crossings for the global floorplan planner, from its
# hierarchical synthesis (OPENROAD_HIERARCHICAL=1, the blocks kept
# modules anywhere below the top), as a tab-separated dump
# parent_json.py turns into parent.json:
#
#   parent <top module>
#   glue   <um2>                     every cell in no block
#   module <instance> <module> <um2> each block instance
#   cross  <from> <from inst> <from bus> <from bits> <to> <to inst> <to bus>
#          <to bits> <via> <depth> <glue_ps>
#
# A block is an instance of a module EXTRACT_BLOCKS names (all the top's
# own children when it names none); everything else is the parent's
# logic, the glue, whatever module it sits in. From every output bus of
# every block, forward through the glue's wires and combinational cells:
# another block's input bus (via wire or comb), a glue register (to the
# glue, inst "reg") or a top output (to the top, inst "-"). Into every
# input bus of every block, backward the same way: a glue register or a
# top input. A crossing through a glue register is two, each to the glue.
# <from bits> counts the bus's bits that leave the block, <to bits> the
# destination bits reached. glue_ps (EXTRACT_TIMING, on by default) is the
# glue's own delay, the worst arrival at the destination bus's nets less
# the worst at the source's, every input at 0, no wire.
#
#   EXTRACT_OUT     the dump
#   EXTRACT_BLOCKS  the blocks' modules
#   EXTRACT_DEPTH   glue cells a crossing is followed through (64)
#   EXTRACT_TIMING  0: no glue_ps (no timing update on a large parent)
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb

set out [open $::env(EXTRACT_OUT) w]
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set top [$block getTopModule]
set top_name [$top getName]
set depth_max [expr { [info exists ::env(EXTRACT_DEPTH)] ? $::env(EXTRACT_DEPTH) : 64 }]
set timing [expr { ![info exists ::env(EXTRACT_TIMING)] || $::env(EXTRACT_TIMING) != 0 }]
puts $out "parent\t$top_name"

proc module_name { mi } {
  # a uniquified module is <module>$<parent>.<instance>
  return [lindex [split [[$mi getMaster] getName] "\$"] 0]
}
proc bus_of { name } {
  regsub {\[[0-9]+\]$} $name "" bus
  return $bus
}

# the blocks: instances of the named modules, or the top's children
set names {}
if { [info exists ::env(EXTRACT_BLOCKS)] && $::env(EXTRACT_BLOCKS) ne "" } {
  set names $::env(EXTRACT_BLOCKS)
}
set blocks {}
foreach mi [$block getModInsts] {
  if { ([llength $names] == 0 && [$mi getParent] eq $top) ||
       ([llength $names] > 0 && [lsearch -exact $names [module_name $mi]] >= 0) } {
    lappend blocks $mi
  }
}
set block_of_mi [dict create]
foreach mi $blocks { dict set block_of_mi [$mi getId] $mi }
if { [llength $names] > 0 } {
  set found [lsort -unique [lmap mi $blocks { module_name $mi }]]
  foreach n $names {
    if { [lsearch -exact $found $n] < 0 } {
      error "extract_parent: EXTRACT_BLOCKS names $n, which no instance below $top_name is"
    }
  }
}

# a cell's block, by its module, cached: "" for the glue
set block_of_module [dict create]
proc block_of { inst } {
  set mod [$inst getModule]
  set id [$mod getId]
  if { [dict exists $::block_of_module $id] } { return [dict get $::block_of_module $id] }
  set b ""
  set mi [$mod getModInst]
  while { $mi ne "NULL" } {
    if { [dict exists $::block_of_mi [$mi getId]] } { set b $mi; break }
    set mi [[$mi getParent] getModInst]
  }
  dict set ::block_of_module $id $b
  return $b
}

set area [dict create]
set glue 0.0
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set a [expr { double([$m getWidth]) * [$m getHeight] / $dbu / $dbu }]
  set b [block_of $inst]
  if { $b eq "" } {
    set glue [expr { $glue + $a }]
  } else {
    set k [$b getId]
    dict set area $k [expr { ([dict exists $area $k] ? [dict get $area $k] : 0.0) + $a }]
  }
}
puts $out "glue\t[format %.3f $glue]"
foreach mi $blocks {
  set k [$mi getId]
  puts $out "module\t[$mi getHierarchicalName]\t[module_name $mi]\t[format %.3f [expr { [dict exists $area $k] ? [dict get $area $k] : 0.0 }]]"
}

set sequential [dict create]
foreach reg [all_registers -cells] {
  dict set sequential [get_property $reg ref_name] 1
}
set clock_ports {}
foreach clk [all_clocks] {
  foreach s [get_property $clk sources] { lappend clock_ports [get_full_name $s] }
}
set ui_ps [expr { [sta::time_ui_sta 1.0] * 1e12 }]
if { $timing } {
  set inputs [all_inputs -no_clocks]
  if { [llength $inputs] > 0 } { set_input_delay 0 -clock [lindex [all_clocks] 0] $inputs }
}
proc net_arrival { net } {
  if { !$::timing || $net eq "NULL" } { return 0.0 }
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

# each block's boundary bits on the parent's side, by flat net
set ins [dict create]
set buses_out [dict create]
set buses_in [dict create]
foreach mi $blocks {
  foreach t [$mi getModITerms] {
    set n [$t getModNet]
    if { $n eq "NULL" } { continue }
    set flat [$n findRelatedNet]
    if { $flat eq "NULL" || [$flat getSigType] ne "SIGNAL" } { continue }
    set key [list [$mi getId] [bus_of [$t getName]]]
    if { [[$t getChildModBTerm] getIoType] eq "INPUT" } {
      dict lappend ins [$flat getId] [list $mi [$t getName]]
      dict lappend buses_in $key $flat
    } else {
      dict lappend buses_out $key $flat
    }
  }
}

proc emit { from from_inst from_bus from_bits to to_inst to_bus to_bits via depth ps } {
  puts $::out "cross\t$from\t$from_inst\t$from_bus\t$from_bits\t$to\t$to_inst\t$to_bus\t$to_bits\t$via\t$depth\t[format %.1f [expr { max(0.0, $ps) }]]"
}

# forward from a block's output bus through the glue's combinational cells
proc forward { mi bus nets } {
  set src [$mi getId]
  set t0 0.0
  foreach n $nets { set t0 [expr { max($t0, [net_arrival $n]) }] }
  set reached [dict create]
  set seen [dict create]
  set todo [lmap n $nets { list $n 0 }]
  while { [llength $todo] > 0 } {
    set next {}
    foreach item $todo {
      lassign $item net depth
      if { [dict exists $seen [$net getId]] } { continue }
      dict set seen [$net getId] 1
      set via [expr { $depth > 0 ? "comb" : "wire" }]
      if { [dict exists $::ins [$net getId]] } {
        foreach e [dict get $::ins [$net getId]] {
          lassign $e to bit
          if { [$to getId] == $src } { continue }
          set k [list [module_name $to] [$to getHierarchicalName] [bus_of $bit] $via]
          dict set reached $k $bit [list $depth [net_arrival $net]]
        }
      }
      foreach bt [$net getBTerms] {
        if { [$bt getIoType] eq "OUTPUT" } {
          dict set reached [list $::top_name - [bus_of [$bt getName]] $via] [$bt getName] [list $depth 0.0]
        }
      }
      if { $depth >= $::depth_max } { continue }
      foreach it [$net getITerms] {
        if { ![$it isInputSignal] } { continue }
        set inst [$it getInst]
        if { [block_of $inst] ne "" } { continue }
        if { [dict exists $::sequential [[$inst getMaster] getName]] } {
          dict set reached [list $::top_name reg "" reg] [$inst getName] [list $depth 0.0]
          continue
        }
        foreach o [$inst getITerms] {
          if { [$o isOutputSignal] && [$o getNet] ne "NULL" } {
            lappend next [list [$o getNet] [expr { $depth + 1 }]]
          }
        }
      }
    }
    set todo $next
  }
  set from_bits [llength $nets]
  dict for {k bits} $reached {
    lassign $k to to_inst to_bus via
    set depth 0
    set t1 0.0
    dict for {b dt} $bits {
      lassign $dt d t
      set depth [expr { max($depth, $d) }]
      set t1 [expr { max($t1, $t) }]
    }
    set ps [expr { $via eq "comb" && $to_inst ne "reg" && $to_inst ne "-" ? $t1 - $t0 : 0.0 }]
    emit [module_name $mi] [$mi getHierarchicalName] $bus $from_bits $to $to_inst $to_bus [dict size $bits] $via $depth $ps
  }
}

# backward into a block's input bus: the glue registers and top inputs
# its combinational fan-in starts at
proc backward { mi bus nets } {
  set regs [dict create]
  set ports [dict create]
  set seen [dict create]
  set todo [lmap n $nets { list $n 0 }]
  set depth_seen 0
  while { [llength $todo] > 0 } {
    set next {}
    foreach item $todo {
      lassign $item net depth
      if { [dict exists $seen [$net getId]] } { continue }
      dict set seen [$net getId] 1
      foreach bt [$net getBTerms] {
        if { [$bt getIoType] eq "INPUT" && [lsearch -exact $::clock_ports [$bt getName]] < 0 } {
          dict set ports [bus_of [$bt getName]] [$bt getName] 1
          set depth_seen [expr { max($depth_seen, $depth) }]
        }
      }
      if { $depth >= $::depth_max } { continue }
      foreach it [$net getITerms] {
        if { ![$it isOutputSignal] } { continue }
        set inst [$it getInst]
        if { [block_of $inst] ne "" } { continue }
        if { [dict exists $::sequential [[$inst getMaster] getName]] } {
          dict set regs [$inst getName] 1
          set depth_seen [expr { max($depth_seen, $depth) }]
          continue
        }
        foreach i [$inst getITerms] {
          if { [$i isInputSignal] && [$i getNet] ne "NULL" } {
            lappend next [list [$i getNet] [expr { $depth + 1 }]]
          }
        }
      }
    }
    set todo $next
  }
  set t1 0.0
  foreach n $nets { set t1 [expr { max($t1, [net_arrival $n]) }] }
  set bits [llength $nets]
  if { [dict size $regs] > 0 } {
    emit $::top_name reg "" [dict size $regs] [module_name $mi] [$mi getHierarchicalName] $bus $bits reg $depth_seen $t1
  }
  dict for {pbus pins} $ports {
    emit $::top_name - $pbus [dict size $pins] [module_name $mi] [$mi getHierarchicalName] $bus $bits \
      [expr { $depth_seen > 0 ? "comb" : "wire" }] $depth_seen 0.0
  }
}

dict for {key nets} $buses_out {
  lassign $key id bus
  forward [dict get $block_of_mi $id] $bus $nets
}
dict for {key nets} $buses_in {
  lassign $key id bus
  backward [dict get $block_of_mi $id] $bus $nets
}
close $out
puts "extract_parent: $top_name, [llength $blocks] blocks, written to $::env(EXTRACT_OUT)"
