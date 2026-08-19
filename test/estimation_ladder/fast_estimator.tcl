set design [file tail $::env(ODB_FILE)]
set sdc [file tail $::env(SDC_FILE)]
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]

set start_time [clock clicks -milliseconds]

# 1. Basic Floorplan
if {[info exists ::env(DIE_AREA)]} { unset ::env(DIE_AREA) }
if {[info exists ::env(CORE_AREA)]} { unset ::env(CORE_AREA) }

if {![info exists ::env(CORE_UTILIZATION)]} { set ::env(CORE_UTILIZATION) 40 }
if {![info exists ::env(CORE_ASPECT_RATIO)]} { set ::env(CORE_ASPECT_RATIO) 1 }
if {![info exists ::env(CORE_MARGIN)]} { set ::env(CORE_MARGIN) 1.0 }

set ::env(SKIP_REPAIR_TIE_FANOUT) 1
set ::env(REMOVE_ABC_BUFFERS) 0

# Just let the flow handle floorplan properly
source $::env(SCRIPTS_DIR)/floorplan.tcl

# 2. Place Pins
if {![info exists ::env(IO_ROUTING_LAYER)]} { set ::env(IO_ROUTING_LAYER) "M4" }
if {![info exists ::env(IO_ROUTING_LAYER_VER)]} { set ::env(IO_ROUTING_LAYER_VER) "M5" }
place_pins -hor_layers $::env(IO_ROUTING_LAYER) -ver_layers $::env(IO_ROUTING_LAYER_VER)

# 3. Global Place (Parameterized)
if {[info exists ::env(RUN_PLACE)] && $::env(RUN_PLACE) == 1} {
    set gp_args "-density $::env(PLACE_DENSITY) -pad_left 0 -pad_right 0 -force_center_initial_place"
    if {[info exists ::env(PLACE_TIMING)] && $::env(PLACE_TIMING) == 1} {
        append gp_args " -timing_driven"
    }
    if {[info exists ::env(PLACE_ROUTABILITY)] && $::env(PLACE_ROUTABILITY) == 1} {
        append gp_args " -routability_driven"
    }
    eval global_placement $gp_args
}

# 4. Global Route (Parameterized)
if {[info exists ::env(RUN_GRT)] && $::env(RUN_GRT) == 1} {
    set grt_iters 0
    if {[info exists ::env(GRT_ITERATIONS)]} { set grt_iters $::env(GRT_ITERATIONS) }
    global_route -congestion_iterations $grt_iters
}

# 5. Parasitics
if {[info exists ::env(RUN_GRT)] && $::env(RUN_GRT) == 1} {
    estimate_parasitics -global_routing
} else {
    estimate_parasitics -placement
}

set end_time [clock clicks -milliseconds]
set elapsed_time [expr {$end_time - $start_time}]
puts "FAST_ESTIMATOR_RUNTIME: $elapsed_time ms"

# Measure Target Paths
set sampled_file [string trim $::env(GROUND_TRUTH_JSON) "'\""]
set fp [open $sampled_file r]
set path_data [read $fp]
close $fp

# Extremely hacky JSON parse for Tcl
set target_paths []
foreach line [split $path_data "\n"] {
    if {[regexp {"start": "([^"]+)", "end": "([^"]+)"} $line match start end]} {
        lappend target_paths [list $start $end]
    }
}

set out_fp [open $::env(OUTPUT_JSON) w]
puts $out_fp "{"
puts $out_fp "\"runtime_ms\": $elapsed_time,"
puts $out_fp "\"paths\": \["

set is_first 1
foreach pt $target_paths {
    set start [lindex $pt 0]
    set end [lindex $pt 1]
    
    # Do not use catch, fail loudly if paths are not found!
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
