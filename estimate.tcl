# The <flow>_estimate report: a fast, deterministic estimate of what
# this floorplan can achieve, produced WITHOUT running the flow's
# expensive tail. Thesis, calibration status and limits:
# docs/estimate.md.
#
# Runs as an orfs_run off the floorplan stage in its own process, so
# it cannot perturb any flow artifact, and it parallelizes with the
# place stage by construction. Pre-route estimates are uniformly
# optimistic: the numbers are for DIFFERENTIAL use (this commit vs
# merge-base, this nightly vs yesterday) where the bias cancels, not
# for sign-off.
#
# The global placement is non-timing-driven and early-stopped at
# overflow 0.6: ranking power saturates there (measured -- see
# docs/estimate.md), and the remaining iterations buy convergence the
# estimate does not need.

source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

# Pin placement: temporary, for wirelength realism. The result is
# discarded with this process. IO_CONSTRAINTS is optional per
# variables.yaml; everything else is config-guaranteed and read
# directly -- absence is an error worth failing on.
if { [env_var_exists_and_non_empty IO_CONSTRAINTS] } {
    log_cmd source $::env(IO_CONSTRAINTS)
}
log_cmd place_pins -hor_layers $::env(IO_PLACER_H) \
    -ver_layers $::env(IO_PLACER_V)

set density_lb_addon [place_density_with_lb_addon]

log_cmd global_placement -density $density_lb_addon -overflow 0.6

estimate_parasitics -placement
set_propagated_clock [all_clocks]

set wns_path [find_timing_paths -path_group reg2reg -sort_by_slack \
    -group_path_count 1]
if { [llength $wns_path] == 0 } {
    error "estimate: no reg2reg timing paths; the platform SDC defines\
        no reg2reg group for this design"
}
set wns [get_property [lindex $wns_path 0] slack]
set clk_period [get_property [lindex [get_clocks] 0] period]
set est_achievable [expr { $clk_period - $wns }]

set block [ord::get_db_block]
set core [$block getCoreArea]
set dbu [expr { double([$block getDbUnitsPerMicron]) }]
set core_um2 [expr { [$core dx] * [$core dy] / ($dbu * $dbu) }]
set cell_um2 0.0
set num_macros 0
foreach inst [$block getInsts] {
    if { [[$inst getMaster] isBlock] } { incr num_macros }
    set bbox [$inst getBBox]
    set cell_um2 [expr { $cell_um2 + [$bbox getDX] * [$bbox getDY] / ($dbu * $dbu) }]
}
set utilization [expr { $cell_um2 / $core_um2 }]

set time_unit "[sta::unit_scale_abbreviation time][sta::unit_suffix time]"

set out [file join $::env(WORK_HOME) $::env(OUTPUT)]
set fp [open $out w]
puts $fp "{"
puts $fp " \"time_unit\": \"$time_unit\","
puts $fp " \"clock_target\": $clk_period,"
puts $fp " \"est_achievable_raw\": $est_achievable,"
puts $fp " \"wns\": $wns,"
puts $fp " \"utilization\": [format %.4f $utilization],"
puts $fp " \"core_um2\": [format %.1f $core_um2],"
puts $fp " \"cell_um2\": [format %.1f $cell_um2],"
puts $fp " \"num_macros\": $num_macros,"
puts $fp " \"place_density\": $::env(PLACE_DENSITY),"
puts $fp " \"density_lb_addon\": $density_lb_addon,"
puts $fp " \"gp_overflow_target\": 0.6"
puts $fp "}"
close $fp

puts "estimate: clock target ${clk_period}${time_unit}\
 (est. achievable, pre-route optimistic: [format %.1f $est_achievable]${time_unit}),\
 utilization [format %.1f [expr { $utilization * 100 }]]%,\
 density $::env(PLACE_DENSITY) (lb+addon $density_lb_addon)."
