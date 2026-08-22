source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]

set start_time [clock clicks -milliseconds]

# 1. Floorplan
initialize_floorplan -utilization $::env(CORE_UTILIZATION) \
    -aspect_ratio $::env(CORE_ASPECT_RATIO) \
    -core_space $::env(CORE_MARGIN) \
    -site $::env(PLACE_SITE)

source $::env(MAKE_TRACKS)

# 2. Place Pins
place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)

# 3. Global Placement (Parameterized via environment)
if {$::env(RUN_PLACE) == 1} {
    set gp_args "-density $::env(PLACE_DENSITY) -pad_left 0 -pad_right 0 -force_center_initial_place"
    if {$::env(PLACE_TIMING) == 1} {
        append gp_args " -timing_driven"
    }
    if {$::env(PLACE_ROUTABILITY) == 1} {
        append gp_args " -routability_driven"
    }
    eval global_placement $gp_args
}

# 4. Global Routing (Parameterized via environment)
if {$::env(RUN_GRT) == 1} {
    global_route -congestion_iterations $::env(GRT_ITERATIONS)
}

# 5. Parasitics
if {$::env(RUN_GRT) == 1} {
    estimate_parasitics -global_routing
} elseif {$::env(RUN_PLACE) == 1} {
    estimate_parasitics -placement
}

set end_time [clock clicks -milliseconds]
set elapsed_time [expr {$end_time - $start_time}]
puts "ESTIMATOR_RUNTIME: $elapsed_time ms"

# Measure Target Paths against Ground Truth using idiomatic json parser
package require json

set fp [open $::env(GROUND_TRUTH_JSON) r]
set gt_dict [json::json2dict [read $fp]]
close $fp

set out_fp [open $::env(OUTPUT_JSON) w]
puts $out_fp "{"
puts $out_fp "\"runtime_ms\": $elapsed_time,"
puts $out_fp "\"paths\": \["

set is_first 1
foreach pt [dict get $gt_dict paths] {
    set start [dict get $pt start]
    set end [dict get $pt end]
    
    set paths [find_timing_paths -from $start -to $end]

    if {[llength $paths] > 0} {
        set slack [sta::format_time [[[lindex $paths 0] path] slack] 4]
    } else {
        set slack 0.0
    }
    
    if {$is_first == 0} { puts $out_fp "," }
    set is_first 0
    puts -nonewline $out_fp "  {\"start\": \"$start\", \"end\": \"$end\", \"slack\": $slack}"
}
puts $out_fp ""
puts $out_fp "\]"
puts $out_fp "}"
close $out_fp

exit 0
