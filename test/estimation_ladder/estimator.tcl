source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $::env(ODB_FILE)]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail

set start_time [clock clicks -milliseconds]

# 1. Floorplan
initialize_floorplan -die_area $::env(DIE_AREA) \
    -core_area $::env(CORE_AREA) \
    -site $::env(PLACE_SITE)

if {$::env(MAKE_TRACKS) ne ""} {
    source $::env(MAKE_TRACKS)
}

# 2. Place Pins
source $::env(IO_CONSTRAINTS)
place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)

# 3. Macro Placement (mirrors ORFS macro_place_util.tcl)
if {[find_macros] != ""} {
    lassign $::env(MACRO_PLACE_HALO) halo_x halo_y
    rtl_macro_placer \
        -halo_width $halo_x \
        -halo_height $halo_y \
        -target_util [place_density_with_lb_addon]
}

if {$::env(RUN_PLACE) == 1} {
    set gp_args "-density $::env(PLACE_DENSITY) -pad_left 0 -pad_right 0 -force_center_initial_place"
    if {$::env(GPL_TIMING_DRIVEN) == 1} {
        append gp_args " -timing_driven"
    }
    if {$::env(GPL_ROUTABILITY_DRIVEN) == 1} {
        append gp_args " -routability_driven"
    }
    eval global_placement $gp_args
}

# 4. Global Routing (Parameterized via environment)
if {$::env(RUN_GRT) == 1} {
    set grt_iters $::env(GRT_ITERATIONS)
    global_route -congestion_iterations $grt_iters
}

# 5. Parasitics
if {$::env(RUN_GRT) == 1} {
    estimate_parasitics -global_routing
} elseif {$::env(RUN_PLACE) == 1} {
    estimate_parasitics -placement
}

set end_time [clock clicks -milliseconds]
set elapsed_s [expr {($end_time - $start_time) / 1000.0}]
puts "ESTIMATOR_RUNTIME: $elapsed_s s"

# Measure Target Paths against Ground Truth
set sampled_file [string trim $::env(GROUND_TRUTH_JSON) "'\""]
set fp [open $sampled_file r]
set path_data [read $fp]
close $fp

set target_paths []
foreach line [split $path_data "\n"] {
    if {[regexp {"start": "([^"]+)", "end": "([^"]+)"} $line match start end]} {
        lappend target_paths [list $start $end]
    }
}

set out_fp [open $::env(OUTPUT_JSON) w]
puts $out_fp "{"
puts $out_fp "\"runtime_s\": $elapsed_s,"
puts $out_fp "\"paths\": \["

set is_first 1
foreach pt $target_paths {
    set start [lindex $pt 0]
    set end [lindex $pt 1]
    set paths [find_timing_paths -sort_by_slack -group_path_count 1 -from $start -to $end]

    if {[llength $paths] == 0} {
        error "No timing path found from $start to $end"
    }
    set slack [get_property [lindex $paths 0] slack]
    set clk_period [get_property [lindex [get_clocks] 0] period]
    set min_period [expr {$clk_period - $slack}]

    if {$is_first == 0} { puts $out_fp "," }
    set is_first 0
    puts -nonewline $out_fp "  {\"start\": \"$start\", \"end\": \"$end\", \"min_period\": $min_period}"
}
puts $out_fp ""
puts $out_fp "\]"
puts $out_fp "}"
close $out_fp

exit 0
