# The reference: the whole synthesised netlist, timed in one session, the
# way part.tcl and top.tcl time it.
#
#   PSTA_NETLIST    the netlist(s): the merged 1_2_yosys.v, or a module's
#                   partition and every partition below it
#   PSTA_TOP        the top module's name
#   PSTA_ENDPOINTS  out: "<pin> <slack>" of every register data pin
#   PSTA_STATS      out: cell count, wall time and peak memory, JSON
#   plus PSTA_LIBS and PSTA_CLOCKS (common.tcl)

source [file join [file dirname [info script]] common.tcl]

psta_read_libs
foreach netlist $::env(PSTA_NETLIST) { read_verilog $netlist }
link_design $::env(PSTA_TOP)
# a module without registers (pure decode logic) has no reg2reg path to
# time; one with registers and no clock found is an error
if { ![psta_clocks] && [llength [all_registers]] } {
  error "flat.tcl: no clock port of PSTA_CLOCKS on $::env(PSTA_TOP)"
}
set nends [psta_endpoints $::env(PSTA_ENDPOINTS) [dict create]]
set f [open $::env(PSTA_STATS) w]
puts $f [psta_json [dict create module $::env(PSTA_TOP) \
  cells [llength [get_cells -hierarchical -quiet -filter "is_hierarchical == 0" *]] \
  endpoints $nends seconds [psta_seconds] peak_mib [psta_peak_mib]]]
close $f
