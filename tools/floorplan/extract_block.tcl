# A synthesised block's facts for the global floorplan planner, as a
# tab-separated dump block_json.py turns into <block>.block.json:
#
#   var   <name> <value>            the floorplan variables the block's flow reads
#   site  <w_um> <h_um>             the placement site
#   area  <std_um2>                 every instance that is not a hard object
#   port  <bterm> <dir>             every signal port bit
#   clock <port> <period_ps>
#   in2reg  <bus> <ps> <bit>        worst input -> first register, per bus
#   reg2out <bus> <ps> <bit>        worst clock -> last register -> output
#   in2out  <bus> <to bus> <ps> <bits>  combinational feedthrough pairs
#   hard  <inst> <master> <w_um> <h_um> <kind>
#   hpin  <inst> <pin bus> <side> <lo_um> <hi_um> <bits> <layer>
#   hnet  <inst> <pin bus> <port bus> <bits> <via> <depth>
#
# Timing is the netlist's own delay, not slack: every input arrives at 0
# and paths are reported unconstrained, so a constraint the block's SDC
# puts on a boundary (set_max_delay, an input delay) does not move it.
#
#   EXTRACT_OUT      the dump
#   EXTRACT_TIMING   0 skips the three timing sweeps
#   EXTRACT_DEPTH    cells a hard object's pin is traced through (32)
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb

set out [open $::env(EXTRACT_OUT) w]
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
proc um { v } { return [format %.3f [expr { double($v) / $::dbu }]] }

puts $out "block\t[$block getName]"
# the floorplan stage's variables, which a synthesis stage does not carry:
# floorplan_extract passes them as EXTRACT_<name>
foreach v {CORE_UTILIZATION CORE_ASPECT_RATIO CORE_MARGIN DIE_AREA CORE_AREA
  RTLMP_MIN_CHANNEL_SIZE PLACE_DENSITY} {
  foreach e [list EXTRACT_$v $v] {
    if { [info exists ::env($e)] && $::env($e) ne "" } {
      puts $out "var\t$v\t$::env($e)"
      break
    }
  }
}
set site NULL
foreach lib [[ord::get_db] getLibs] {
  set s [$lib findSite $::env(PLACE_SITE)]
  if { $s ne "NULL" } { set site $s }
}
puts $out "site\t[um [$site getWidth]]\t[um [$site getHeight]]"

proc bus_of { name } {
  regsub {\[[0-9]+\]$} $name "" bus
  return $bus
}

# hard objects: a master of class BLOCK (a memory, a register file, a
# hardened macro)
set std 0.0
set hard {}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  if { [$m isBlock] } {
    lappend hard $inst
  } else {
    set std [expr { $std + double([$m getWidth]) * [$m getHeight] }]
  }
}
puts $out "area\t[format %.3f [expr { $std / $dbu / $dbu }]]"

# get_property reports times in the liberty's unit
set ui_ps [expr { [sta::time_ui_sta 1.0] * 1e12 }]
set clock_ports {}
foreach clk [all_clocks] {
  foreach src [get_property $clk sources] {
    lappend clock_ports [get_full_name $src]
    puts $out "clock\t[get_full_name $src]\t[format %.1f [expr { [get_property $clk period] * $ui_ps }]]"
  }
}

set buses_in [dict create]
set buses_out [dict create]
foreach bt [$block getBTerms] {
  if { [$bt getSigType] ne "SIGNAL" } { continue }
  set name [$bt getName]
  if { [lsearch -exact $clock_ports $name] >= 0 } { continue }
  set dir [string tolower [$bt getIoType]]
  puts $out "port\t$name\t$dir"
  if { $dir eq "input" } {
    dict lappend buses_in [bus_of $name] $name
  } elseif { $dir eq "output" } {
    dict lappend buses_out [bus_of $name] $name
  }
}

proc path_ps { pe } {
  set pts [get_property $pe points]
  set a0 [get_property [lindex $pts 0] arrival]
  set a1 [get_property [lindex $pts end] arrival]
  return [format %.1f [expr { ($a1 - $a0) * $::ui_ps }]]
}

if { ![info exists ::env(EXTRACT_TIMING)] || $::env(EXTRACT_TIMING) != 0 } {
  set clk [lindex [all_clocks] 0]
  set inputs [all_inputs -no_clocks]
  if { [llength $inputs] > 0 } { set_input_delay 0 -clock $clk $inputs }
  set data_pins [all_registers -data_pins]
  set clock_pins [all_registers -clock_pins]
  dict for {bus pins} $buses_in {
    set ports [get_ports $pins]
    if { [llength $data_pins] > 0 } {
      foreach pe [find_timing_paths -from $ports -to $data_pins -unconstrained \
        -path_delay max -group_path_count 1] {
        set start [get_full_name [get_property $pe startpoint]]
        puts $out "in2reg\t$bus\t[path_ps $pe]\t$start"
      }
    }
    set worst [dict create]
    foreach pe [find_timing_paths -from $ports -to [all_outputs] -unconstrained \
      -path_delay max -group_path_count 100000 -endpoint_path_count 1] {
      set to [bus_of [get_full_name [get_property $pe endpoint]]]
      set ps [path_ps $pe]
      if { ![dict exists $worst $to] } { dict set worst $to [list 0.0 0] }
      lassign [dict get $worst $to] w n
      dict set worst $to [list [expr { max($w, $ps) }] [expr { $n + 1 }]]
    }
    dict for {to wn} $worst {
      puts $out "in2out\t$bus\t$to\t[lindex $wn 0]\t[lindex $wn 1]"
    }
  }
  if { [llength $clock_pins] > 0 } {
    dict for {bus pins} $buses_out {
      foreach pe [find_timing_paths -from $clock_pins -to [get_ports $pins] \
        -unconstrained -path_delay max -group_path_count 1] {
        set end [get_full_name [get_property $pe endpoint]]
        puts $out "reg2out\t$bus\t[path_ps $pe]\t$end"
      }
    }
  }
}

# a hard object's pins, by bus, on the side of its outline they sit on
proc pin_side { box w h } {
  set d [dict create W [$box xMin] E [expr { $w - [$box xMax] }] \
    S [$box yMin] N [expr { $h - [$box yMax] }]]
  set best W
  foreach s {W E S N} {
    if { [dict get $d $s] < [dict get $d $best] } { set best $s }
  }
  return $best
}

set depth_max [expr { [info exists ::env(EXTRACT_DEPTH)] ? $::env(EXTRACT_DEPTH) : 32 }]
set fanout_max 256
set sequential [dict create]
foreach reg [all_registers -cells] {
  dict set sequential [get_property $reg ref_name] 1
}

# The ports a hard object's pin bus reaches through the block's cells:
# forward from an output pin, backward from an input pin, through
# combinational cells and at most one register, up to depth_max cells.
proc trace { iterms forward } {
  set reached [dict create]
  set seen [dict create]
  set todo {}
  foreach it $iterms {
    set net [$it getNet]
    if { $net ne "NULL" } { lappend todo [list $net 0 0] }
  }
  while { [llength $todo] > 0 } {
    set next {}
    foreach item $todo {
      lassign $item net depth regs
      set key "[$net getId]/$regs"
      if { [dict exists $seen $key] } { continue }
      dict set seen $key 1
      if { [$net getSigType] ne "SIGNAL" } { continue }
      if { [llength [$net getITerms]] > $::fanout_max } { continue }
      foreach bt [$net getBTerms] {
        set dir [string tolower [$bt getIoType]]
        if { ($forward && $dir eq "output") || (!$forward && $dir eq "input") } {
          set name [$bt getName]
          set via [expr { $regs ? "reg" : "comb" }]
          set k [list [bus_of $name] $via]
          if { ![dict exists $reached $k] } { dict set reached $k [list [dict create] $depth] }
          lassign [dict get $reached $k] bits d
          dict set bits $name 1
          dict set reached $k [list $bits [expr { max($d, $depth) }]]
        }
      }
      if { $depth >= $::depth_max } { continue }
      foreach it [$net getITerms] {
        if { [[$it getMTerm] getSigType] ne "SIGNAL" } { continue }
        set inst [$it getInst]
        set m [$inst getMaster]
        if { [$m isBlock] } { continue }
        if { $forward && ![$it isInputSignal] } { continue }
        if { !$forward && ![$it isOutputSignal] } { continue }
        set r $regs
        if { [dict exists $::sequential [$m getName]] } {
          if { $regs } { continue }
          set r 1
        }
        foreach o [$inst getITerms] {
          if { [[$o getMTerm] getSigType] ne "SIGNAL" } { continue }
          if { ($forward && [$o isOutputSignal]) || (!$forward && [$o isInputSignal]) } {
            set n [$o getNet]
            if { $n ne "NULL" } { lappend next [list $n [expr { $depth + 1 }] $r] }
          }
        }
      }
    }
    set todo $next
  }
  return $reached
}

foreach inst $hard {
  set m [$inst getMaster]
  set w [$m getWidth]
  set h [$m getHeight]
  set name [$inst getName]
  set kind [expr { [regexp -nocase {ram|mem|sram} [$m getName]] ? "memory" : "macro" }]
  puts $out "hard\t$name\t[$m getName]\t[um $w]\t[um $h]\t$kind"
  set pins [dict create]
  foreach it [$inst getITerms] {
    set mt [$it getMTerm]
    if { [$mt getSigType] ne "SIGNAL" } { continue }
    set net [$it getNet]
    if { $net ne "NULL" && [$net getSigType] eq "CLOCK" } { continue }
    dict lappend pins [bus_of [$mt getName]] $it
  }
  dict for {bus its} $pins {
    set lo ""
    set hi ""
    set side ""
    set layer ""
    foreach it $its {
      set box [[$it getMTerm] getBBox]
      set s [pin_side $box $w $h]
      if { $side eq "" } { set side $s }
      foreach mp [[$it getMTerm] getMPins] {
        foreach g [$mp getGeometry] {
          set l [$g getTechLayer]
          if { $l ne "NULL" } { set layer [$l getName] }
        }
      }
      set a [expr { $s in {N S} ? [$box xMin] : [$box yMin] }]
      set b [expr { $s in {N S} ? [$box xMax] : [$box yMax] }]
      if { $lo eq "" || $a < $lo } { set lo $a }
      if { $hi eq "" || $b > $hi } { set hi $b }
    }
    puts $out "hpin\t$name\t$bus\t$side\t[um $lo]\t[um $hi]\t[llength $its]\t$layer"
    set forward [[lindex $its 0] isOutputSignal]
    dict for {k v} [trace $its $forward] {
      lassign $k pbus via
      lassign $v bits depth
      puts $out "hnet\t$name\t$bus\t$pbus\t[dict size $bits]\t$via\t$depth"
    }
  }
}
close $out
puts "extract_block: [$block getName] written to $::env(EXTRACT_OUT)"
