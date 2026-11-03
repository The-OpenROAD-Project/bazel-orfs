# The kit's facts, read from the kit's own files: what README.pdf says
# about the netlist is counted here, never typed.
#
# openroad -exit kit_facts.tcl, with the environment:
#   KIT_LEFS     the technology LEF first, then cells' and macros' LEFs
#   KIT_LIBS     every liberty file of the kit
#   KIT_NETLIST  the kit's netlist
#   KIT_TOP      its top module
#   KIT_SDC      the kit's SDC
#   KIT_OUT      the JSON to write
#
# Stops when the netlist does not link against the kit's own LEF and
# liberty: an instance of a master the kit does not ship is a kit that
# cannot be implemented, found here rather than by the reader.

foreach lef $::env(KIT_LEFS) { read_lef $lef }
foreach lib $::env(KIT_LIBS) { read_liberty $lib }
read_verilog $::env(KIT_NETLIST)
link_design $::env(KIT_TOP)
# the SDC reads on its own: nothing of an ORFS environment left in it
read_sdc $::env(KIT_SDC)

set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]

# What stops a place-and-route tool or silently changes what it times:
# combinational loops, registers no clock reaches, a register two clocks
# reach. Counted with OpenSTA's check_setup (arguments: no_input_delay
# no_output_delay multiple_clock no_clock unconstrained loops
# generated_clocks).
proc check_count { args } {
  set n 0
  foreach error [sta::check_timing_cmd {*}$args] {
    set objs [lsearch -all -inline -not -glob [lrange $error 1 end] {[|-]*}]
    set count [llength $objs]
    regexp {There (?:is|are) (\d+) } [lindex $error 0] -> count
    incr n $count
  }
  return $n
}
set loops [check_count 0 0 0 0 0 1 0]
set no_clock [check_count 0 0 0 1 0 0 0]
set multiple_clock [check_count 0 0 1 0 0 0 0]
if { $loops > 0 } {
  error "kit_facts: $loops combinational loops in the kit's netlist"
}

# Nets a place-and-route tool cannot implement as they are: a load with
# no driver, two drivers on one net.
set undriven 0
set multidriven 0
foreach net [$block getNets] {
  if { [$net getSigType] in {POWER GROUND} } { continue }
  set drivers 0
  set loads 0
  foreach iterm [$net getITerms] {
    if { [$iterm isOutputSignal] } { incr drivers } elseif { [$iterm isInputSignal] } { incr loads }
  }
  foreach bterm [$net getBTerms] {
    if { [$bterm getIoType] eq "INPUT" } { incr drivers } else { incr loads }
  }
  if { $drivers == 0 && $loads > 0 } { incr undriven }
  if { $drivers > 1 } { incr multidriven }
}
if { $multidriven > 0 } {
  error "kit_facts: $multidriven nets with more than one driver in the kit's netlist"
}

proc json_str { s } {
  return "\"[string map {\\ \\\\ \" \\\"} $s]\""
}

set ports 0
foreach bterm [$block getBTerms] {
  if { [$bterm getSigType] in {POWER GROUND} } { continue }
  incr ports
}

set cells 0
set flops 0
set clock_gates 0
set std_area 0.0
set macros {}
set masters_seen {}
foreach inst [$block getInsts] {
  set master [$inst getMaster]
  set name [$master getName]
  if { [$master isBlock] } {
    dict lappend macros $name [$inst getName]
    if { ![dict exists $masters_seen $name] } {
      dict set masters_seen $name [list \
        [expr { [$master getWidth] / double($dbu) }] \
        [expr { [$master getHeight] / double($dbu) }]]
    }
    continue
  }
  incr cells
  set std_area [expr { $std_area + [$master getWidth] * [$master getHeight] / double($dbu) / $dbu }]
  if { [string match ICG* $name] } {
    incr clock_gates
  } elseif { [$master isSequential] } {
    incr flops
  }
}

# a count of zero is a counter that is broken, not a core without flops
if { $flops == 0 || $cells == 0 } {
  error "kit_facts: $cells cells and $flops flip-flops counted; the count is broken"
}

set f [open $::env(KIT_OUT) w]
puts $f "\{"
puts $f "  \"top\": [json_str $::env(KIT_TOP)],"
puts $f "  \"ports\": $ports,"
puts $f "  \"cells\": $cells,"
puts $f "  \"flops\": $flops,"
puts $f "  \"clock_gates\": $clock_gates,"
puts $f "  \"std_area_um2\": [format %.1f $std_area],"
puts $f "  \"checks\": \{\"loops\": $loops, \"no_clock\": $no_clock, \"multiple_clock\": $multiple_clock, \"undriven\": $undriven, \"multidriven\": $multidriven\},"
puts $f "  \"macros\": \{"
set first 1
foreach name [lsort [dict keys $macros]] {
  lassign [dict get $masters_seen $name] w h
  set insts [lmap i [lsort [dict get $macros $name]] { json_str $i }]
  if { !$first } { puts $f "," }
  set first 0
  puts -nonewline $f "    [json_str $name]: \{\"w_um\": [format %.3f $w], \"h_um\": [format %.3f $h], \"instances\": \[[join $insts {, }]\]\}"
}
puts $f ""
puts $f "  \}"
puts $f "\}"
close $f
puts "kit_facts: $cells cells, $flops flops, [dict size $macros] macro shapes, $ports ports"
