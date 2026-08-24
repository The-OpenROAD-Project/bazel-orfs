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

# Every rung of the ladder is gated by an environment variable so the
# Optuna study owns the search space and this script stays a thin,
# faithful mirror of the ORFS stages it approximates.  Knob *values* are
# passed as ready-made argument strings (GP_ARGS, GRT_ARGS, ...) rather
# than one variable per option: the study composes them, and adding a
# knob to the sweep does not mean touching this file.
proc est_flag { name {default 0} } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

proc est_args { name } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return ""
}

# Per-phase runtimes.  A single total cannot say which knob bought which
# second, and the runtime surrogate in the study models the phases
# separately (they depend on disjoint knob subsets) rather than treating
# the total as one black box.
set ::phase_times [dict create]

proc time_phase { name body } {
    set t0 [clock clicks -milliseconds]
    uplevel 1 $body
    set t1 [clock clicks -milliseconds]
    dict set ::phase_times $name [expr {($t1 - $t0) / 1000.0}]
}

set start_time [clock clicks -milliseconds]

# 1. Floorplan
time_phase floorplan {
    initialize_floorplan -die_area $::env(DIE_AREA) \
        -core_area $::env(CORE_AREA) \
        -site $::env(PLACE_SITE)

    if {$::env(MAKE_TRACKS) ne ""} {
        source $::env(MAKE_TRACKS)
    }
}

# 2. Parasitics calibration.  estimate_parasitics -placement turns
# wirelength into delay through the RC that set_wire_rc installs; which
# layer stands in for "an average wire" is a free parameter, and
# WIRE_RC_LAYER_OVERRIDE lets the study sweep it.
if {[est_args WIRE_RC_LAYER_OVERRIDE] ne ""} {
    set_wire_rc -signal -layer $::env(WIRE_RC_LAYER_OVERRIDE)
}

# 3. Place Pins.  With -place_ios the pins are co-optimized with the
# cells inside global placement, but gpl leaves them off-track, so
# place_pins still has to run -- afterwards, to legalize what gpl chose,
# instead of beforehand to fix locations gpl must then live with.
set place_ios [est_flag PLACE_IOS 0]

proc est_place_pins { } {
    source $::env(IO_CONSTRAINTS)
    place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)
}

if {$place_ios != 1} {
    time_phase place_pins { est_place_pins }
}

# 4. Macro Placement (mirrors ORFS macro_place_util.tcl).  Gated: with
# macros present this is not free, and leaving it unconditional made the
# "synthesis only" rung silently include a full RTLMP run.
if {[est_flag RUN_MACRO_PLACE 1] == 1 && [find_macros] != ""} {
    time_phase macro_place {
        lassign $::env(MACRO_PLACE_HALO) halo_x halo_y
        set mp_args [list -halo_width $halo_x -halo_height $halo_y \
            -target_util [place_density_with_lb_addon]]
        eval rtl_macro_placer $mp_args [est_args RTLMP_ARGS]
    }
}

# 5. Global Placement
if {[est_flag RUN_PLACE 0] == 1} {
    time_phase global_place {
        # Follow ORFS's padding rather than pinning it to 0: the ground
        # truth was placed with it, and a different pad spreads the cells
        # differently than the flow being estimated.  The variable is
        # scoped to the place/floorplan stages and this script runs off
        # the synth target, so fall back to ORFS's own default of 0
        # instead of failing on an unset variable.
        set cell_pad [est_flag CELL_PAD_IN_SITES_GLOBAL_PLACEMENT 0]
        set gp_args "-density [place_density_with_lb_addon]"
        append gp_args " -pad_left $cell_pad -pad_right $cell_pad"
        append gp_args " -force_center_initial_place"

        # -place_ios is a branch, not another dimension: gpl rejects it
        # together with -timing_driven and -routability_driven.
        if {$place_ios == 1} {
            append gp_args " -place_ios"
        } else {
            if {[est_flag GPL_TIMING_DRIVEN 0] == 1} {
                append gp_args " -timing_driven"
            }
            if {[est_flag GPL_ROUTABILITY_DRIVEN 0] == 1} {
                append gp_args " -routability_driven"
            }
        }
        if {[est_flag GPL_VIRTUAL_CTS 0] == 1} {
            append gp_args " -virtual_cts"
        }
        append gp_args " [est_args GP_ARGS]"

        eval global_placement $gp_args
    }

    if {$place_ios == 1} {
        time_phase place_pins { est_place_pins }
    }

    estimate_parasitics -placement
}

# 6. Clock tree.  The ground truth is a post-CTS ODB read back with
# propagated clocks, so an ideal clock here does not merely lose skew: on
# a design with macros the clock insertion latency does not cancel and
# lands directly in min_period = clk_period - slack.  CLOCK_MODE picks
# how much of that gap to buy back:
#   none        - ideal clock (the old behaviour, kept as a rung)
#   propagated  - set_propagated_clock with no tree to propagate
#   real        - clock_tree_synthesis, as ORFS runs it
# The virtual clock tree is gpl's -virtual_cts (GPL_VIRTUAL_CTS above),
# since it happens inside global placement rather than after it.
set clock_mode [est_flag CLOCK_MODE none]

if {$clock_mode eq "real"} {
    time_phase cts {
        # ORFS runs CTS on a legalized placement (3_place.odb).  Whether
        # TritonCTS tolerates raw global-placement output is what
        # CTS_DPL exists to measure.
        if {[est_flag CTS_DPL 0] == 1} {
            detailed_placement
        }
        repair_clock_inverters
        set cts_args [list -sink_clustering_enable -repair_clock_nets]
        eval clock_tree_synthesis $cts_args [est_args CTS_ARGS_EXTRA]
        # Order follows ORFS cts.tcl: re-estimate straight after CTS,
        # which has just inserted buffers and dummy loads, and only then
        # propagate the clock.
        estimate_parasitics -placement
        set_propagated_clock [all_clocks]
        estimate_parasitics -placement
    }
} elseif {$clock_mode eq "propagated"} {
    set_propagated_clock [all_clocks]
}

# Re-estimate against whichever source is current.  repair_design and
# repair_timing open an incremental-parasitics guard that errors out
# (EST-0104) if anything upstream -- CTS inserting buffers and dummy
# loads, most notably -- left parasitics invalid.
proc est_refresh_parasitics { } {
    if {[est_flag RUN_GRT 0] == 1 && [grt::have_routes]} {
        estimate_parasitics -global_routing
    } else {
        estimate_parasitics -placement
    }
}

# 7. Repair design.  The ground-truth ODB has been through repair_design
# and repair_timing; without them the estimate carries a systematic
# optimism no placement knob can remove.
if {[est_flag RUN_REPAIR_DESIGN 0] == 1} {
    time_phase repair_design {
        est_refresh_parasitics
        eval repair_design [est_args REPAIR_DESIGN_ARGS]
        est_refresh_parasitics
    }
}

# 8. Global Routing
if {[est_flag RUN_GRT 0] == 1} {
    time_phase global_route {
        set grt_args "-congestion_iterations [est_flag GRT_ITERATIONS 1]"
        append grt_args " [est_args GRT_ARGS]"
        eval global_route $grt_args
    }
    estimate_parasitics -global_routing
}

# 9. Repair timing.  Hold repair is deliberately absent: the metric is
# the minimum clock period, so -hold can only cost runtime.
if {[est_flag RUN_REPAIR_TIMING 0] == 1} {
    time_phase repair_timing {
        est_refresh_parasitics
        eval repair_timing -setup [est_args REPAIR_TIMING_ARGS]
        est_refresh_parasitics
    }
}

set end_time [clock clicks -milliseconds]
set estimate_s [expr {($end_time - $start_time) / 1000.0}]
dict set ::phase_times load $load_s

# Measure Target Paths against Ground Truth.  Deliberately after
# end_time: the study measures how long until a timing signal is
# available, not how long it takes to interrogate it.
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

set sta_start [clock clicks -milliseconds]
set measured []
foreach pt $target_paths {
    set start [lindex $pt 0]
    set end [lindex $pt 1]
    set paths [find_timing_paths -sort_by_slack -group_path_count 1 -from $start -to $end]

    if {[llength $paths] == 0} {
        error "No timing path found from $start to $end"
    }
    set slack [get_property [lindex $paths 0] slack]
    set clk_period [get_property [lindex [get_clocks] 0] period]
    lappend measured [list $start $end [expr {$clk_period - $slack}]]
}
# OpenSTA builds the timing graph and computes delays on the first
# query, so this is not bookkeeping around the result -- it is where a
# large part of the work happens, and on a rung that runs no flow stages
# it is very nearly all of it.
set sta_s [expr {([clock clicks -milliseconds] - $sta_start) / 1000.0}]
dict set ::phase_times sta $sta_s

set total_s [expr {$load_s + $estimate_s + $sta_s}]
puts "ESTIMATOR_RUNTIME: $total_s s (load $load_s, estimate $estimate_s, sta $sta_s)"

set out_fp [open $::env(OUTPUT_JSON) w]
puts $out_fp "{"
puts $out_fp "\"runtime_s\": $total_s,"
puts $out_fp "\"load_s\": $load_s,"
puts $out_fp "\"estimate_s\": $estimate_s,"
puts $out_fp "\"sta_s\": $sta_s,"
puts $out_fp "\"phases\": \{"
set phase_first 1
foreach {phase_name phase_s} $::phase_times {
    if {$phase_first == 0} { puts $out_fp "," }
    set phase_first 0
    puts -nonewline $out_fp "  \"$phase_name\": $phase_s"
}
puts $out_fp ""
puts $out_fp "\},"
puts $out_fp "\"paths\": \["

set is_first 1
foreach m $measured {
    lassign $m start end min_period
    if {$is_first == 0} { puts $out_fp "," }
    set is_first 0
    puts -nonewline $out_fp "  {\"start\": \"$start\", \"end\": \"$end\", \"min_period\": $min_period}"
}
puts $out_fp ""
puts $out_fp "\]"
puts $out_fp "}"
close $out_fp

exit 0
