# The clock starts here, not after the design is loaded.  What the study
# claims to measure is how long it takes to get a timing number out of a
# post-synthesis netlist, and reading the ODB, the SDC and the liberties
# is part of that.  Excluding it flattered the cheap rungs enormously --
# a rung that runs no flow stages at all was being reported at 0.024s
# when nearly all of its real cost is the load and the timing query --
# and it made the comparison unfair besides, since the flow baseline is
# summed from stage logs that each include their own load.
set script_start [clock clicks -milliseconds]

source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $::env(ODB_FILE)]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail
set load_s [expr {([clock clicks -milliseconds] - $script_start) / 1000.0}]

# Knob overlay for batch mode; empty here, so est_flag/est_args fall back
# to the environment exactly as before.
set ::est_cfg [dict create]
set ::phase_times [dict create]

source $::env(ESTIMATOR_LIB_TCL)

set start_time [clock clicks -milliseconds]

# 1. Floorplan.  Common to every configuration -- in batch mode it is the
# root of the tree and is paid exactly once.
time_phase floorplan {
    initialize_floorplan -die_area $::env(DIE_AREA) \
        -core_area $::env(CORE_AREA) \
        -site $::env(PLACE_SITE)

    if {$::env(MAKE_TRACKS) ne ""} {
        source $::env(MAKE_TRACKS)
    }
}

# Batch mode: walk a whole tree of configurations in this one process,
# forking at each divergence so a shared stage is paid exactly once.  One
# leaf JSON per configuration lands in EST_RESULTS_DIR.
if {[info exists ::env(EST_MANIFEST_DIR)] && $::env(EST_MANIFEST_DIR) ne ""} {
    source $::env(ESTIMATOR_BATCH_TCL)
    exit 0
}

est_stage_wire_rc
est_stage_pins_pre
est_stage_macro_place
est_stage_global_place
est_stage_clock
est_stage_repair_design
est_stage_grt
est_stage_repair_timing

set end_time [clock clicks -milliseconds]
set estimate_s [expr {($end_time - $start_time) / 1000.0}]
dict set ::phase_times load $load_s

est_measure_paths
set sta_s [dict get $::phase_times sta]

set total_s [expr {$load_s + $estimate_s + $sta_s}]
puts "ESTIMATOR_RUNTIME: $total_s s (load $load_s, estimate $estimate_s, sta $sta_s)"

est_write_json $::env(OUTPUT_JSON) $load_s $estimate_s $sta_s

exit 0
