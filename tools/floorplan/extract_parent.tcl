# The parent's crossings for the global floorplan planner, from its
# hierarchical synthesis (OPENROAD_HIERARCHICAL=1, the blocks kept
# modules anywhere below the top), as a tab-separated dump
# parent_json.py turns into parent.json:
#
#   parent <top module>
#   glue   <um2>                     every cell in no block
#   module <instance> <module> <um2> each block instance
#   key    <key> <instance> <module> each block
#   bit    <key> <bus> <bit> <input|output> <net> <arrival_ps>
#   port   <name> <input|output> <net>   the top's ports but its clocks
#   cell   <reg|comb> <input nets> <output nets>  each glue cell
#
# A block is an instance of a module EXTRACT_BLOCKS names (all the top's
# own children when it names none), or an instance of a macro master of
# that name (a parent synthesised over its blocks' mocks or abstracts);
# everything else is the parent's logic, the glue, whatever module it
# sits in. parent_json.py searches the graph: from every output bus of
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
#   EXTRACT_TIMING  0: no glue_ps (no timing update on a large parent)
#   EXTRACT_BLOCK_DUMPS  files <dir>/<master>.dump.tsv: each macro
#                   block's own dump in extract_block.tcl's records (its
#                   outline as DIE_AREA, its ports), for block_json.py
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb

set out [open $::env(EXTRACT_OUT) w]
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set top [$block getTopModule]
set top_name [$top getName]
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
# a block is a key: m<id> for a module instance, i<id> for a macro
# instance; its name and module by key
set blocks {}
set block_name [dict create]
set block_module [dict create]
set block_hard [dict create]
foreach mi [$block getModInsts] {
  if { ([llength $names] == 0 && [$mi getParent] eq $top) ||
       ([llength $names] > 0 && [lsearch -exact $names [module_name $mi]] >= 0) } {
    set k m[$mi getId]
    lappend blocks $k
    dict set block_name $k [$mi getHierarchicalName]
    dict set block_module $k [module_name $mi]
    dict set block_hard $k $mi
  }
}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  if { ![$m isBlock] } { continue }
  if { ([llength $names] == 0 && [$inst getModule] eq $top) ||
       ([llength $names] > 0 && [lsearch -exact $names [$m getName]] >= 0) } {
    set k i[$inst getId]
    lappend blocks $k
    dict set block_name $k [$inst getName]
    dict set block_module $k [$m getName]
    dict set block_hard $k $inst
  }
}
set block_of_mi [dict create]
foreach k $blocks { dict set block_of_mi $k 1 }

if { [llength $names] > 0 } {
  set found [lsort -unique [dict values $block_module]]
  foreach n $names {
    if { [lsearch -exact $found $n] < 0 } {
      error "extract_parent: EXTRACT_BLOCKS names $n, which no instance below $top_name is"
    }
  }
}

# a cell's block, by its module, cached: "" for the glue
set block_of_module [dict create]
proc block_of { inst } {
  if { [dict exists $::block_of_mi i[$inst getId]] } { return i[$inst getId] }
  set mod [$inst getModule]
  set id [$mod getId]
  if { [dict exists $::block_of_module $id] } { return [dict get $::block_of_module $id] }
  set b ""
  set mi [$mod getModInst]
  while { $mi ne "NULL" } {
    if { [dict exists $::block_of_mi m[$mi getId]] } { set b m[$mi getId]; break }
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
    set k $b
    dict set area $k [expr { ([dict exists $area $k] ? [dict get $area $k] : 0.0) + $a }]
  }
}
puts $out "glue\t[format %.3f $glue]"
foreach k $blocks {
  puts $out "module\t[dict get $block_name $k]\t[dict get $block_module $k]\t[format %.3f [expr { [dict exists $area $k] ? [dict get $area $k] : 0.0 }]]"
}

set sequential [dict create]
foreach reg [all_registers -cells] {
  dict set sequential [get_property $reg ref_name] 1
}
set ui_ps [expr { [sta::time_ui_sta 1.0] * 1e12 }]
set clock_ports {}
set clock_period [dict create]
foreach clk [all_clocks] {
  foreach s [get_property $clk sources] {
    lappend clock_ports [get_full_name $s]
    dict set clock_period [get_full_name $s] [format %.1f [expr { [get_property $clk period] * $ui_ps }]]
  }
}

# a macro block's own facts, as extract_block.tcl writes them for a
# synthesised block: its outline is the macro's, its ports the master's
if { [info exists ::env(EXTRACT_BLOCK_DUMPS)] && $::env(EXTRACT_BLOCK_DUMPS) ne "" } {
  set dumps [dict create]
  foreach d $::env(EXTRACT_BLOCK_DUMPS) {
    dict set dumps [file rootname [file rootname [file tail $d]]] $d
  }
  set site NULL
  foreach lib [[ord::get_db] getLibs] {
    set s [$lib findSite $::env(PLACE_SITE)]
    if { $s ne "NULL" } { set site $s }
  }
  set written [dict create]
  foreach k $blocks {
    if { [string index $k 0] ne "i" } { continue }
    set m [[dict get $block_hard $k] getMaster]
    if { [dict exists $written [$m getName]] || ![dict exists $dumps [$m getName]] } { continue }
    dict set written [$m getName] 1
    set f [open [dict get $dumps [$m getName]] w]
    puts $f "block\t[$m getName]"
    puts $f "var\tDIE_AREA\t0 0 [format %.3f [expr { double([$m getWidth]) / $dbu }]] [format %.3f [expr { double([$m getHeight]) / $dbu }]]"
    if { $site ne "NULL" } {
      puts $f "site\t[format %.3f [expr { double([$site getWidth]) / $dbu }]]\t[format %.3f [expr { double([$site getHeight]) / $dbu }]]"
    }
    puts $f "area\t0.000"
    foreach it [[dict get $block_hard $k] getITerms] {
      set mt [$it getMTerm]
      if { [$mt getSigType] ni {SIGNAL CLOCK} } { continue }
      set clock ""
      if { [$it getNet] ne "NULL" } {
        foreach bt [[$it getNet] getBTerms] {
          if { [dict exists $clock_period [$bt getName]] } { set clock [$bt getName] }
        }
      }
      if { $clock ne "" } {
        puts $f "clock\t[$mt getName]\t[dict get $clock_period $clock]"
      } else {
        puts $f "port\t[$mt getName]\t[string tolower [$mt getIoType]]"
      }
    }
    close $f
  }
  dict for {n d} $dumps {
    if { ![dict exists $written $n] } {
      error "extract_parent: EXTRACT_BLOCK_DUMPS names $n, which no macro block is"
    }
  }
}
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

# the graph parent_json.py searches: every block boundary bit with its
# net's arrival, every top port, every glue cell with its nets
foreach k $blocks {
  puts $out "key\t$k\t[dict get $block_name $k]\t[dict get $block_module $k]"
}
proc bit { k bus name io flat } {
  if { $flat eq "NULL" || [$flat getSigType] ne "SIGNAL" } { return }
  puts $::out "bit\t$k\t$bus\t$name\t[string tolower $io]\t[$flat getId]\t[format %.3f [net_arrival $flat]]"
}
foreach k $blocks {
  set obj [dict get $block_hard $k]
  if { [string index $k 0] eq "m" } {
    foreach t [$obj getModITerms] {
      set n [$t getModNet]
      if { $n eq "NULL" } { continue }
      bit $k [bus_of [$t getName]] [$t getName] [[$t getChildModBTerm] getIoType] [$n findRelatedNet]
    }
  } else {
    foreach t [$obj getITerms] {
      set mt [$t getMTerm]
      bit $k [bus_of [$mt getName]] [$mt getName] [$mt getIoType] [$t getNet]
    }
  }
}
foreach bt [$block getBTerms] {
  set n [$bt getNet]
  if { $n eq "NULL" || [lsearch -exact $clock_ports [$bt getName]] >= 0 } { continue }
  puts $out "port\t[$bt getName]\t[string tolower [$bt getIoType]]\t[$n getId]"
}
foreach inst [$block getInsts] {
  if { [block_of $inst] ne "" } { continue }
  set ins {}
  set outs {}
  foreach it [$inst getITerms] {
    set n [$it getNet]
    if { $n eq "NULL" } { continue }
    if { [$it isInputSignal] } {
      lappend ins [$n getId]
    } elseif { [$it isOutputSignal] } {
      lappend outs [$n getId]
    }
  }
  set seq [expr { [dict exists $sequential [[$inst getMaster] getName]] ? "reg" : "comb" }]
  puts $out "cell\t$seq\t[join $ins ,]\t[join $outs ,]"
}
close $out
puts "extract_parent: $top_name, [llength $blocks] blocks, written to $::env(EXTRACT_OUT)"
