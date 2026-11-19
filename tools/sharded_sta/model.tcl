# One kept module's timing model: its partition and those below it linked,
# timed with the ideal clock of PSTA_CLOCKS and zero input and output
# delays, and written as a liberty cell named after the module.
#
#   PSTA_NETLIST  the subtree's partition netlists
#   PSTA_TOP      the module
#   PSTA_MODEL    out: the liberty file
#   PSTA_STATS    out: cells, write and wall seconds, peak memory, JSON
#   PSTA_THREADS  the threads the timer uses
#   plus PSTA_LIBS and PSTA_CLOCKS (module_sta's common.tcl)

source [file join [file dirname [info script]] .. module_sta common.tcl]

set link_make_black_boxes 0
sta::set_thread_count $::env(PSTA_THREADS)
psta_read_libs
foreach netlist $::env(PSTA_NETLIST) { read_verilog $netlist }
link_design $::env(PSTA_TOP)
psta_clocks
set clock_ports [get_ports -quiet [dict keys [dict create {*}$::env(PSTA_CLOCKS)]]]
set inputs {}
foreach p [all_inputs] {
  if { [lsearch -exact [get_full_name $clock_ports] [get_full_name $p]] < 0 } { lappend inputs $p }
}
set clk [lindex [all_clocks] 0]
if { $clk ne "" } {
  if { [llength $inputs] } { set_input_delay 0 -clock $clk $inputs }
  if { [llength [all_outputs]] } { set_output_delay 0 -clock $clk [all_outputs] }
}
set t0 [psta_seconds]
write_timing_model -cell_name $::env(PSTA_TOP) $::env(PSTA_MODEL)
set f [open $::env(PSTA_STATS) w]
puts $f [psta_json [dict create module $::env(PSTA_TOP) \
  cells [llength [get_cells -hierarchical -quiet -filter "is_hierarchical == 0" *]] \
  write_seconds [expr { [psta_seconds] - $t0 }] seconds [psta_seconds] peak_mib [psta_peak_mib]]]
close $f
