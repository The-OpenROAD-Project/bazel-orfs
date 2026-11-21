# A synthesised block's signal netlist for rung 1 of the planner's ladder,
# as a tab-separated dump netlist.py reads:
#
#   b <name>                   the block
#   c <id> <seq> <hard>        every instance: a register, a hard object
#   p <id> <name> <dir>        every signal port bit but the clocks
#   n <drivers> <sinks> [name] every signal net of two or more pins but the
#                              clock nets; comma-separated ends, an
#                              instance by its id, a port as p<id>; the
#                              name of a net of HIGH_FANOUT sinks or more
#
#   EXTRACT_OUT   the dump
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb

set out [open $::env(EXTRACT_OUT) w]
set block [ord::get_db_block]
puts $out "b\t[$block getName]"

set seq_masters [dict create]
foreach reg [all_registers -cells] {
  dict set seq_masters [get_property $reg ref_name] 1
}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set seq [dict exists $seq_masters [$m getName]]
  puts $out "c\t[$inst getId]\t$seq\t[$m isBlock]"
}

set high_fanout 64
set clock_nets [dict create]
set clock_ports {}
foreach clk [all_clocks] {
  foreach src [get_property $clk sources] {
    lappend clock_ports [get_full_name $src]
  }
}
set clock_pins [all_registers -clock_pins]
if { [llength $clock_pins] > 0 } {
  foreach n [get_nets -quiet -of_objects $clock_pins] {
    dict set clock_nets [get_full_name $n] 1
  }
}
foreach bt [$block getBTerms] {
  if { [$bt getSigType] ne "SIGNAL" } { continue }
  set name [$bt getName]
  if { [lsearch -exact $clock_ports $name] >= 0 } {
    if { [$bt getNet] ne "NULL" } { dict set clock_nets [[$bt getNet] getName] 1 }
    continue
  }
  puts $out "p\t[$bt getId]\t$name\t[string tolower [$bt getIoType]]"
}

foreach net [$block getNets] {
  if { [$net getSigType] ne "SIGNAL" } { continue }
  if { [dict exists $clock_nets [$net getName]] } { continue }
  set drv {}
  set snk {}
  foreach it [$net getITerms] {
    if { [[$it getMTerm] getSigType] ne "SIGNAL" } { continue }
    if { [$it isOutputSignal] } {
      lappend drv [[$it getInst] getId]
    } else {
      lappend snk [[$it getInst] getId]
    }
  }
  foreach bt [$net getBTerms] {
    if { [$bt getIoType] eq "INPUT" } {
      lappend drv "p[$bt getId]"
    } else {
      lappend snk "p[$bt getId]"
    }
  }
  if { [llength $drv] + [llength $snk] < 2 } { continue }
  if { [llength $snk] >= $high_fanout } {
    puts $out "n\t[join $drv ,]\t[join $snk ,]\t[$net getName]"
  } else {
    puts $out "n\t[join $drv ,]\t[join $snk ,]"
  }
}
close $out
puts "extract_netlist: [$block getName] written to $::env(EXTRACT_OUT)"
