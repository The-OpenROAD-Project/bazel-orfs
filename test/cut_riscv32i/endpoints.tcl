# Every reg2reg endpoint's period at global route (the clock period minus
# its slack), with the route's parasitics and the clock tree propagated:
# the measure ORFS #4583 proposes, and the population compare.py reads.
# One line per endpoint, "<endpoint>\t<period ps>", to ENDPOINTS_OUT.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_1_grt.odb 5_1_grt.sdc
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing
set p [get_property [lindex [all_clocks] 0] period]
# register to register, selected explicitly: the flow defines no path
# groups, and -path_group names one only where an SDC made it
set ends [find_timing_paths -from [all_registers -clock_pins] \
  -to [all_registers -data_pins] -endpoint_path_count 1 \
  -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint]
set f [open $::env(ENDPOINTS_OUT) w]
foreach t $ends {
  puts $f [format "%s\t%.1f" [get_full_name [get_property $t endpoint]] \
    [expr { $p - [get_property $t slack] }]]
}
close $f
