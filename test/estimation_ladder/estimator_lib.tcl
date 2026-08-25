# Shared estimator machinery: knob lookup, per-phase timing, the flow
# stages, path measurement and the leaf JSON writer.  estimator.tcl runs
# these once for a single configuration; estimator_batch.tcl walks a whole
# tree of configurations, forking at each divergence so a shared stage is
# paid exactly once.

# Every rung of the ladder is gated by a knob so the study owns the search
# space and this script stays a thin, faithful mirror of the ORFS stages it
# approximates.  Knob *values* are passed as ready-made argument strings
# (GP_ARGS, GRT_ARGS, ...) rather than one variable per option: the study
# composes them, and adding a knob to the sweep does not mean touching this
# file.  Knobs come from the ::est_cfg overlay (batch mode: the walk fills
# it in stage by stage) and fall back to the environment (single mode: the
# driver passes them as make variables).
proc est_flag { name {default 0} } {
    if { [dict exists $::est_cfg $name] && [dict get $::est_cfg $name] ne "" } {
        return [dict get $::est_cfg $name]
    }
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

proc est_args { name } {
    return [est_flag $name ""]
}

# Per-phase runtimes.  A single total cannot say which knob bought which
# second, and the runtime surrogate in the study models the phases
# separately (they depend on disjoint knob subsets) rather than treating
# the total as one black box.  In batch mode the dict is inherited across
# fork, so a leaf's ::phase_times holds exactly the phases on its own path
# from the root -- per-leaf attribution for free.
proc time_phase { name body } {
    set t0 [clock clicks -milliseconds]
    uplevel 1 $body
    set t1 [clock clicks -milliseconds]
    dict set ::phase_times $name [expr {($t1 - $t0) / 1000.0}]
}

# 2. Parasitics calibration.  estimate_parasitics -placement turns
# wirelength into delay through the RC that set_wire_rc installs; which
# layer stands in for "an average wire" is a free parameter, and
# WIRE_RC_LAYER_OVERRIDE lets the study sweep it.
proc est_stage_wire_rc { } {
    if {[est_args WIRE_RC_LAYER_OVERRIDE] ne ""} {
        set_wire_rc -signal -layer [est_args WIRE_RC_LAYER_OVERRIDE]
    }
}

# 3. Place Pins.  With -place_ios the pins are co-optimized with the
# cells inside global placement, but gpl leaves them off-track, so
# place_pins still has to run -- afterwards, to legalize what gpl chose,
# instead of beforehand to fix locations gpl must then live with.
proc est_place_pins { } {
    source $::env(IO_CONSTRAINTS)
    place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)
}

proc est_stage_pins_pre { } {
    if {[est_flag PLACE_IOS 0] != 1} {
        time_phase place_pins { est_place_pins }
    }
}

# 4. Macro Placement (mirrors ORFS macro_place_util.tcl).  Gated: with
# macros present this is not free, and leaving it unconditional made the
# "synthesis only" rung silently include a full RTLMP run.
proc est_stage_macro_place { } {
    if {[est_flag RUN_MACRO_PLACE 1] == 1 && [find_macros] != ""} {
        time_phase macro_place {
            lassign $::env(MACRO_PLACE_HALO) halo_x halo_y
            set mp_args [list -halo_width $halo_x -halo_height $halo_y \
                -target_util [place_density_with_lb_addon]]
            eval rtl_macro_placer $mp_args [est_args RTLMP_ARGS]
        }
    }
}

# 5. Global Placement
proc est_stage_global_place { } {
    set place_ios [est_flag PLACE_IOS 0]
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
proc est_stage_clock { } {
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
proc est_stage_repair_design { } {
    if {[est_flag RUN_REPAIR_DESIGN 0] == 1} {
        time_phase repair_design {
            est_refresh_parasitics
            eval repair_design [est_args REPAIR_DESIGN_ARGS]
            est_refresh_parasitics
        }
    }
}

# 8. Global Routing
proc est_stage_grt { } {
    if {[est_flag RUN_GRT 0] == 1} {
        time_phase global_route {
            set grt_args "-congestion_iterations [est_flag GRT_ITERATIONS 1]"
            append grt_args " [est_args GRT_ARGS]"
            eval global_route $grt_args
        }
        estimate_parasitics -global_routing
    }
}

# 9. Repair timing.  Hold repair is deliberately absent: the metric is
# the minimum clock period, so -hold can only cost runtime.
proc est_stage_repair_timing { } {
    if {[est_flag RUN_REPAIR_TIMING 0] == 1} {
        time_phase repair_timing {
            est_refresh_parasitics
            eval repair_timing -setup [est_args REPAIR_TIMING_ARGS]
            est_refresh_parasitics
        }
    }
}

# Per-path features, for the question calibration cannot touch.
#
# Any correction that reads only the estimate is a monotone function of
# it and so cannot reorder the paths -- which is exactly what the
# estimator gets wrong.  Reordering needs to know something about the
# individual path, and the obvious candidate is how far it physically
# reaches: the error is wire-related, and a path whose endpoints sit far
# apart has more room for the router to add detour than a local one.
# Gated because it costs an ODB lookup per path and only the feature
# study wants it.
proc est_pin_xy { name } {
    set blk [ord::get_db_block]
    # Split on the last separator and go via the instance: findITerm on
    # the block does not resolve the names OpenSTA reports for escaped
    # Verilog identifiers like sum_stage1[2][78]$_DFF_PP0_/QN.
    # ODB stores escaped Verilog identifiers -- sum_stage1\[0\]\[42\] --
    # while OpenSTA reports them unescaped, so a direct lookup of the
    # name STA gives back finds nothing at all.
    set idx [string last "/" $name]
    if {$idx > 0} {
        set inst_name [string range $name 0 [expr {$idx - 1}]]
        set term_name [string range $name [expr {$idx + 1}] end]
        set inst [$blk findInst $inst_name]
        if {$inst eq "NULL"} {
            set inst [$blk findInst \
                [string map [list "\[" "\\\[" "\]" "\\\]"] $inst_name]]
        }
        if {$inst ne "NULL"} {
            set it [$inst findITerm $term_name]
            if {$it ne "NULL"} {
                set is_macro [[$inst getMaster] isBlock]
                set net [$it getNet]
                set fan [expr {$net eq "NULL" ? 0 : [$net getITermCount]}]
                lassign [$it getAvgXY] ok x y
                if {$ok} { return [list $x $y $is_macro $fan] }
                lassign [$inst getOrigin] x y
                return [list $x $y $is_macro $fan]
            }
        }
    }
    set bt [$blk findBTerm $name]
    if {$bt ne "NULL"} {
        set bb [$bt getBBox]
        return [list [expr {([$bb xMin] + [$bb xMax]) / 2}] \
                     [expr {([$bb yMin] + [$bb yMax]) / 2}] 0 0]
    }
    return {}
}

proc est_features { start end } {
    set a [est_pin_xy $start]
    set b [est_pin_xy $end]
    if {[llength $a] == 0 || [llength $b] == 0} {
        return "\"dist_um\": -1, \"macro_ends\": 0, \"fanout\": 0"
    }
    lassign $a ax ay amacro afan
    lassign $b bx by bmacro bfan
    set dbu [[[ord::get_db] getTech] getDbUnitsPerMicron]
    set dist [expr {(abs($ax - $bx) + abs($ay - $by)) / double($dbu)}]
    return "\"dist_um\": $dist, \"macro_ends\": [expr {$amacro + $bmacro}], \"fanout\": [expr {$afan + $bfan}]"
}

# Measure Target Paths against Ground Truth.  Deliberately outside the
# estimate clock: the study measures how long until a timing signal is
# available, not how long it takes to interrogate it.
proc est_measure_paths { } {
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
    set ::measured []
    foreach pt $target_paths {
        set start [lindex $pt 0]
        set end [lindex $pt 1]
        set paths [find_timing_paths -sort_by_slack -group_path_count 1 -from $start -to $end]

        if {[llength $paths] == 0} {
            error "No timing path found from $start to $end"
        }
        set slack [get_property [lindex $paths 0] slack]
        set clk_period [get_property [lindex [get_clocks] 0] period]
        lappend ::measured [list $start $end [expr {$clk_period - $slack}]]
    }
    # OpenSTA builds the timing graph and computes delays on the first
    # query, so this is not bookkeeping around the result -- it is where a
    # large part of the work happens, and on a rung that runs no flow stages
    # it is very nearly all of it.
    set sta_s [expr {([clock clicks -milliseconds] - $sta_start) / 1000.0}]
    dict set ::phase_times sta $sta_s
}

proc est_write_json { out_json load_s estimate_s sta_s } {
    set total_s [expr {$load_s + $estimate_s + $sta_s}]
    set out_fp [open $out_json w]
    puts $out_fp "{"
    puts $out_fp "\"runtime_s\": $total_s,"
    # From OpenSTA rather than assumed: periods come out in whatever the
    # liberty and SDC use, picoseconds on asap7 and nanoseconds
    # elsewhere, so a report that hardcodes a suffix is wrong by a factor
    # of a thousand on another platform and silently so.
    puts $out_fp "\"time_unit\": \"[sta::unit_scale_abbreviation time][sta::unit_suffix time]\","
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
    foreach m $::measured {
        lassign $m start end min_period
        if {$is_first == 0} { puts $out_fp "," }
        set is_first 0
        set extra ""
        if {[est_flag DUMP_FEATURES 0] == 1} {
            set extra ", [est_features $start $end]"
        }
        puts -nonewline $out_fp "  {\"start\": \"$start\", \"end\": \"$end\", \"min_period\": $min_period$extra}"
    }
    puts $out_fp ""
    puts $out_fp "\]"
    puts $out_fp "}"
    close $out_fp
}
