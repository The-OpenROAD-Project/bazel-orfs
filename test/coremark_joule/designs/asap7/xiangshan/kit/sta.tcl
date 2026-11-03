# Times an implemented XSTile in OpenSTA from the kit's libraries and the
# tool's own outputs, and prints the minimum register-to-register clock
# period, to compare with the period the tool reports.
#
# Run from a bazel-orfs clone, KIT the kit's directory as an absolute
# path, with OpenROAD's OpenSTA:
#   bazelisk run @openroad//src/sta:opensta -- -exit "$KIT/check/sta.tcl"
# and, to print the difference to the tool's number, TOOL_PERIOD_PS set
# to the tool's minimum period in ps. The kit is found from this script's
# own path, so any directory works.
#
# Reads from results/ (or the directory in RESULTS_DIR):
#   *.v          the netlist at global route; hardened blocks' netlists too
#   *.spef       parasitics of the top; blocks' SPEF are listed in blocks.txt
#   XSTile.sdc   the SDC as used (optional: else constraints/XSTile.sdc)
#   lib/*.lib    liberty of any cell or macro not in the kit (optional)
#   blocks.txt   optional, one line per hardened block read as a netlist:
#                <instance path in XSTile> <its SPEF file in results/>
set kit [file normalize [file join [file dirname [info script]] ..]]
set top XSTile
if { [info exists ::env(RESULTS_DIR)] } {
  set res [file normalize $::env(RESULTS_DIR)]
} else {
  set res [file join $kit results]
}
proc need { files what } {
  if { [llength $files] == 0 } { error "sta.tcl: no $what found" }
  return $files
}

# Liberty: the kit's cells and macros, then anything the tool added
set libs [concat [glob -nocomplain -directory [file join $kit cells lib] *.lib *.lib.gz] \
  [glob -nocomplain -directory [file join $kit macros lib] *.lib *.lib.gz] \
  [glob -nocomplain -directory [file join $res lib] *.lib *.lib.gz]]
foreach lib [lsort [need $libs "liberty files"]] { read_liberty $lib }

# Netlist: every Verilog file the tool wrote
foreach v [lsort [need [glob -nocomplain -directory $res *.v *.v.gz] "netlist in $res"]] {
  read_verilog $v
}
link_design $top

set sdc [file join $res $top.sdc]
if { ![file exists $sdc] } { set sdc [file join $kit constraints $top.sdc] }
read_sdc $sdc

# Parasitics: the top's SPEF, then each block's at its instance
set blocks [file join $res blocks.txt]
set block_spefs {}
if { [file exists $blocks] } {
  set f [open $blocks]
  foreach line [split [read $f] "\n"] {
    set line [string trim $line]
    if { $line eq "" || [string index $line 0] eq "#" } { continue }
    lassign $line path spef
    lappend block_spefs $path [file join $res $spef]
  }
  close $f
}
set skip [lmap {path spef} $block_spefs { file normalize $spef }]
set top_spefs {}
foreach s [glob -nocomplain -directory $res *.spef *.spef.gz] {
  if { [lsearch -exact $skip [file normalize $s]] < 0 } { lappend top_spefs $s }
}
if { [llength $top_spefs] != 1 } {
  error "sta.tcl: want one top-level SPEF in $res, found [llength $top_spefs]"
}
# reduced as read: a full RC network per net of the whole tile does not fit
read_spef -reduce [lindex $top_spefs 0]
foreach {path spef} $block_spefs { read_spef -reduce -path $path $spef }
set_propagated_clock [all_clocks]

puts "=== sta.tcl: inputs"
puts "sdc   $sdc"
puts "spef  [lindex $top_spefs 0]"
foreach {path spef} $block_spefs { puts "spef  $spef at $path" }
puts "=== sta.tcl: nets without parasitics (should be none but constants)"
report_parasitic_annotation

# The minimum period: the SDC's period minus the worst slack of every path
# from a register's clock pin to a register's data pin, the same measure the
# OpenROAD reference reports. Boundary paths are budgets, not the period.
set clk [lindex [all_clocks] 0]
set period [get_property $clk period]
set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
set w [lindex [find_timing_paths {*}$r2r -sort_by_slack -group_path_count 1] 0]
set slack [get_property $w slack]
set from [get_full_name [get_property $w startpoint]]
set to [get_full_name [get_property $w endpoint]]
set min_period [expr { $period - $slack }]

puts "=== sta.tcl: worst register-to-register path"
report_checks {*}$r2r -path_delay max -format full_clock_expanded \
  -fields {fanout cap slew} -digits 1
puts "=== sta.tcl: clock skew"
report_clock_skew

puts "=== sta.tcl: result"
puts [format "clock %s, SDC period %.0f ps" [get_full_name $clk] $period]
puts [format "worst reg2reg slack %.0f ps, %s -> %s" $slack $from $to]
puts [format "OpenSTA minimum period %.0f ps" $min_period]
if { [info exists ::env(TOOL_PERIOD_PS)] } {
  set tool $::env(TOOL_PERIOD_PS)
  puts [format "tool minimum period %.0f ps, OpenSTA - tool = %+.0f ps (%+.1f %%)" \
    $tool [expr { $min_period - $tool }] [expr { 100.0 * ($min_period - $tool) / $tool }]]
}
