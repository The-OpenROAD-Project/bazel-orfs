# The <flow>_estimate report: a fast, deterministic estimate of what
# this design can achieve at a given set of floorplan parameters,
# produced from the SYNTHESIS output without running the flow's
# physical stages. Thesis, calibration status, the division of labor
# with ORFS's config.mk pin machinery, and limits: docs/estimate.md.
#
# The floorplan is built here, in-script, from the same environment
# variables the production floorplan stage reads -- so one estimate is
# one point in floorplan-parameter space, and run-time overrides
# (CORE_UTILIZATION=..., PLACE_DENSITY=..., via <flow>_estimate_run)
# sweep the space at one point per one to two minutes. The JSON echoes
# the parameters in force under their exact ORFS variable names, so a
# chosen point is directly consumable by config.mk pin machinery.
#
# Pre-route estimates are uniformly optimistic: the numbers are for
# DIFFERENTIAL and RANKING use, where the bias cancels, not for
# sign-off. The global placement is non-timing-driven and
# early-stopped at overflow 0.6: ranking power saturates there
# (measured -- docs/estimate.md).

source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb 1_synth.sdc

# Floorplan initialization: the production stage's two modes, from the
# same variables. Anything config-guaranteed is read directly --
# absence is an error worth failing on.
if { [env_var_exists_and_non_empty DIE_AREA] } {
    log_cmd initialize_floorplan -die_area $::env(DIE_AREA) \
        -core_area $::env(CORE_AREA) \
        -site $::env(PLACE_SITE)
} elseif { [env_var_exists_and_non_empty CORE_UTILIZATION] } {
    log_cmd initialize_floorplan -utilization $::env(CORE_UTILIZATION) \
        -aspect_ratio $::env(CORE_ASPECT_RATIO) \
        -core_space $::env(CORE_MARGIN) \
        -site $::env(PLACE_SITE)
} else {
    error "estimate: no floorplan initialization method specified\
        (neither DIE_AREA nor CORE_UTILIZATION)"
}
if { [env_var_exists_and_non_empty MAKE_TRACKS] } {
    uplevel #0 [list source $::env(MAKE_TRACKS)]
}

set density_lb_addon [place_density_with_lb_addon]

# Macro placement: the production placer, when the design has macros.
# This is the flow's default draw; selection over a seed population is
# the macro-placement campaign's business.
if { [find_macros] != "" } {
    lassign $::env(MACRO_PLACE_HALO) halo_x halo_y
    log_cmd rtl_macro_placer -halo_width $halo_x -halo_height $halo_y \
        -target_util $density_lb_addon \
        -report_directory [file join $::env(WORK_HOME) rtlmp]
}

# Pin placement: temporary, for wirelength realism. IO_CONSTRAINTS is
# optional per variables.yaml.
if { [env_var_exists_and_non_empty IO_CONSTRAINTS] } {
    log_cmd source $::env(IO_CONSTRAINTS)
}
log_cmd place_pins -hor_layers $::env(IO_PLACER_H) \
    -ver_layers $::env(IO_PLACER_V)

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

# Macro-path channel: the KPI macro placement actually controls.
# Classify a sample of near-critical paths by whether either end lives
# in a macro. ODB escapes Verilog identifiers and OpenSTA does not.
set block [ord::get_db_block]
set macro_insts [dict create]
foreach inst [$block getInsts] {
    if { [[$inst getMaster] isBlock] } {
        dict set macro_insts [string map {"\\" ""} [$inst getName]] 1
    }
}
set num_macros [dict size $macro_insts]
set macro_sum 0.0
set macro_n 0
set macro_worst 0.0
set sampled 0
if { $num_macros > 0 } {
    foreach path [find_timing_paths -path_group reg2reg -sort_by_slack \
        -group_path_count 200] {
        incr sampled
        set is_macro 0
        foreach endname [list \
            [get_full_name [get_property $path startpoint]] \
            [get_full_name [get_property $path endpoint]]] {
            set inst_name [join [lrange [split $endname "/"] 0 end-1] "/"]
            if { [dict exists $macro_insts $inst_name] } {
                set is_macro 1
            }
        }
        if { $is_macro } {
            set period [expr { $clk_period - [get_property $path slack] }]
            set macro_sum [expr { $macro_sum + $period }]
            incr macro_n
            if { $period > $macro_worst } { set macro_worst $period }
        }
    }
}
set macro_mean [expr { $macro_n ? $macro_sum / $macro_n : 0.0 }]

set core [$block getCoreArea]
set dbu [expr { double([$block getDbUnitsPerMicron]) }]
set core_um2 [expr { [$core dx] * [$core dy] / ($dbu * $dbu) }]
set cell_um2 0.0
foreach inst [$block getInsts] {
    set bbox [$inst getBBox]
    set cell_um2 [expr { $cell_um2 + [$bbox getDX] * [$bbox getDY] / ($dbu * $dbu) }]
}
set utilization [expr { $cell_um2 / $core_um2 }]

set time_unit "[sta::unit_scale_abbreviation time][sta::unit_suffix time]"

# The parameters in force, under their exact ORFS variable names: a
# chosen point is directly consumable by config.mk pin machinery.
set param_lines {}
foreach var {DIE_AREA CORE_AREA CORE_UTILIZATION CORE_ASPECT_RATIO
             CORE_MARGIN PLACE_DENSITY PLACE_DENSITY_LB_ADDON} {
    if { [env_var_exists_and_non_empty $var] } {
        lappend param_lines "  \"$var\": \"$::env($var)\""
    }
}

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
puts $fp " \"macro_paths_mean\": [format %.3f $macro_mean],"
puts $fp " \"macro_paths_worst\": [format %.3f $macro_worst],"
puts $fp " \"macro_paths_sampled\": $macro_n,"
puts $fp " \"paths_sampled\": $sampled,"
puts $fp " \"macros_pinned\": [expr { [env_var_exists_and_non_empty MACRO_PLACEMENT_TCL] ? "true" : "false" }],"
puts $fp " \"density_lb_addon\": $density_lb_addon,"
puts $fp " \"gp_overflow_target\": 0.6,"
puts $fp " \"params\": {"
puts $fp [join $param_lines ",\n"]
puts $fp " }"
puts $fp "}"
close $fp

puts "estimate: clock target ${clk_period}${time_unit}\
 (est. achievable, pre-route optimistic: [format %.1f $est_achievable]${time_unit}),\
 macro paths mean [format %.1f $macro_mean]${time_unit} ($macro_n sampled),\
 utilization [format %.1f [expr { $utilization * 100 }]]%,\
 density lb+addon $density_lb_addon."
