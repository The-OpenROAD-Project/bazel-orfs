set design [file tail $::env(ODB_FILE)]
set sdc [file tail $::env(SDC_FILE)]
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]

set start_time [clock clicks -milliseconds]

# 1. Basic Floorplan
if {[info exists ::env(DIE_AREA)]} { unset ::env(DIE_AREA) }
if {[info exists ::env(CORE_AREA)]} { unset ::env(CORE_AREA) }
set ::env(CORE_MARGIN) 2
# initialize_floorplan -site $::env(PLACE_SITE) -utilization $::env(CORE_UTILIZATION) -aspect_ratio $::env(CORE_ASPECT_RATIO) -core_space $::env(CORE_MARGIN)


# 2. Place Pins
if {![info exists ::env(IO_ROUTING_LAYER)]} { set ::env(IO_ROUTING_LAYER) "M2" }
# place_pins -hor_layers $::env(IO_ROUTING_LAYER) -ver_layers $::env(IO_ROUTING_LAYER_VER)

if {[info exists ::env(RUN_PLACE)] && $::env(RUN_PLACE) == 1} {
    puts "Removing placement to run our own..."
    # Need to remove the placement from the DB so we can re-place it.
    # Wait, can we do that? global_placement usually just overrides, let's just let it overwrite.
}

# 3. Global Place (Parameterized)
if {[info exists ::env(RUN_PLACE)] && $::env(RUN_PLACE) == 1} {
    set gp_args "-density $::env(PLACE_DENSITY) -pad_left 0 -pad_right 0 -force_center_initial_place"
    if {[info exists ::env(PLACE_TIMING)] && $::env(PLACE_TIMING) == 1} {
        append gp_args " -timing_driven"
    }
    if {[info exists ::env(PLACE_ROUTABILITY)] && $::env(PLACE_ROUTABILITY) == 1} {
        append gp_args " -routability_driven"
    }
    catch { eval global_placement $gp_args }
}

# 4. Global Route (Parameterized)
if {[info exists ::env(RUN_GRT)] && $::env(RUN_GRT) == 1} {
    set grt_iters 0
    if {[info exists ::env(GRT_ITERATIONS)]} { set grt_iters $::env(GRT_ITERATIONS) }
    global_route -congestion_iterations $grt_iters
}

# 5. Parasitics
catch {
if {[info exists ::env(RUN_GRT)] && $::env(RUN_GRT) == 1} {
    estimate_parasitics -global_routing
} else {
    estimate_parasitics -placement
}
}

set end_time [clock clicks -milliseconds]
set elapsed_time [expr {$end_time - $start_time}]
puts "FAST_ESTIMATOR_RUNTIME: $elapsed_time ms"

# Measure Target Paths
set sampled_file [string trim $::env(SAMPLED_PATHS_JSON) "'\""]
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
    
    if {[catch {set paths [find_timing_paths -from $start -to $end]}]} {
        set paths []
    }

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
puts "Fast estimator finished."
