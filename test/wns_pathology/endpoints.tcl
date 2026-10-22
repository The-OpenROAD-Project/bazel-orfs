# Every reg2reg endpoint's period at global route, its clock's period
# minus its slack, "<endpoint>\t<period>\t<its clock's period>" per line in
# OUT, in the liberty's time unit: the population behind the one path WNS
# reports (ORFS #4583). A design with several clocks (ethmac, an async
# bridge) is read against each endpoint's own clock.
# Loaded as read.tcl loads it.
source $::env(SCRIPTS_DIR)/load.tcl
set ::env(RESULTS_DIR) [file dirname $::env(ODB_FILE)]
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing

set f [open $::env(OUT) w]
if { [llength [all_registers]] } {
  foreach t [find_timing_paths -from [all_registers -clock_pins] \
               -to [all_registers -data_pins] -endpoint_path_count 1 \
               -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint] {
    set clk [get_property $t endpoint_clock]
    if { $clk eq "" || $clk eq "NULL" } { continue }
    set p [get_property $clk period]
    puts $f [format "%s\t%.6g\t%.6g" [get_full_name [get_property $t endpoint]] \
      [expr { $p - [get_property $t slack] }] $p]
  }
}
close $f
