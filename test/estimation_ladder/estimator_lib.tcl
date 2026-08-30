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

# ---------------------------------------------------------------------
# Perturbations, for the seed-sensitivity study.
#
# No stage below exposes a random seed -- OpenROAD is deterministic for
# identical inputs -- so there is no seed to vary.  The literature's
# substitute is to perturb an input by an amount too small to be a
# deliberate design change and read the spread of the outcome: Kahng &
# Mantik (ISQED 2002) for the taxonomy of such perturbations, Jeong &
# Kahng for the 1ps timing-constraint probe, Chan/Kahng/Woo (SLIP 2020)
# for the tiny geometric shift and for the framing as a noise floor --
# a lower bound on how accurate any predictor of this flow can be.
#
# Each perturbation is keyed to ONE stage (CLK_PERIOD_EPS_GRT, not a
# global CLK_PERIOD_EPS) on purpose.  The batch walk groups
# configurations on the knobs each stage consumes, so a per-stage knob
# makes the walk diverge exactly where the perturbation takes effect and
# share the whole prefix above it.  The study therefore costs one full
# run plus the tail below each perturbed stage, instead of a full run per
# data point -- which is what makes per-stage attribution affordable at
# all.  A global knob would fork at the root and throw that away.
proc est_perturb_eps { stage suffix } {
    return [est_flag ${suffix}_[string toupper $stage] 0]
}

# The clock-period nudge, applied at the top of a stage and persisting to
# the end of the run.
#
# This is the cleanest of the perturbations because it cannot move the
# reported metric except through tool noise: est_measure_paths reports
# min_period = clk_period - slack, so a period loosened by eps yields a
# slack larger by eps and the two cancel exactly.  Any movement that
# survives came from a timing-driven decision inside the flow stages
# taking a different branch -- which is the definition of tool noise.
#
# On a stage that reads no timing at all the result must be bit-identical,
# which is this study's null control.  That makes a silently ineffective
# perturbation dangerous: it would pass the null control and then report
# zero noise everywhere.  So the new period is read back and verified,
# and a nudge that failed to land is an error rather than a quiet zero.
proc est_perturb_clock { stage } {
    set eps [est_perturb_eps $stage CLK_PERIOD_EPS]
    if {$eps == 0} {
        return
    }
    set clocks [all_clocks]
    if {[llength $clocks] == 0} {
        error "EST-perturb: CLK_PERIOD_EPS at $stage but the design has no clocks"
    }
    set wanted [dict create]
    foreach clk $clocks {
        set name [get_name $clk]
        set want [expr {[get_property $clk period] + $eps}]
        set sources [get_property $clk sources]
        if {[llength $sources] == 0} {
            error "EST-perturb: clock $name reports no sources, so its\
                period cannot be re-issued; the study would silently\
                measure nothing"
        }
        create_clock -name $name -period $want $sources
        dict set wanted $name $want
    }
    # Read back rather than trust the command.  get_property's "sources"
    # is the one part of this that nothing else in the study relies on,
    # so it is checked instead of assumed -- a nudge that quietly failed
    # to land would pass the null control and then report a noise floor
    # of exactly zero everywhere, which is the one wrong answer that
    # looks like a clean result.
    # The tolerance is relative, not absolute, because OpenSTA keeps the
    # period in a 32-bit float: asking for 1001 reads back as
    # 1000.999939, a relative error of 6e-8, which is float32 epsilon and
    # not a failed perturbation.  A nudge that genuinely did not land is
    # off by the whole of eps, so at 1ps on a 1000ps clock this still
    # discriminates by three orders of magnitude.
    #
    # It does put a floor under the probe: an eps below the period's
    # float32 resolution (~6e-5 at 1000ps) could not be verified, and
    # would not be reliably applied either.  1ps is 16000x above that, so
    # the 1ps figure the literature uses is safely inside the range.
    dict for {name want} $wanted {
        set got [get_property [get_clocks $name] period]
        if {abs($got - $want) > 1e-6 * abs($want)} {
            error "EST-perturb: clock $name period is $got after asking\
                for $want; the perturbation did not take effect"
        }
    }
}

# The geometric nudge, in whole sites and whole rows so the core stays
# row-aligned and initialize_floorplan has nothing to snap or warn about.
# Chan/Kahng/Woo found a slightly moved placement blockage to be their
# strongest noise source (11.5% on routed wirelength), which is the same
# shape of perturbation as moving the core boundary by one site.
#
# Only the upper-right corner moves; the origin stays put, so the
# perturbation is one extra (or one fewer) site column and row rather
# than a translation of the whole core.
proc est_core_area { } {
    set sites [est_flag CORE_AREA_EPS_SITES 0]
    set rows [est_flag CORE_AREA_EPS_ROWS 0]
    if {$sites == 0 && $rows == 0} {
        return $::env(CORE_AREA)
    }
    set site [est_find_site $::env(PLACE_SITE)]
    set dbu [[[ord::get_db] getTech] getDbUnitsPerMicron]
    lassign $::env(CORE_AREA) x0 y0 x1 y1
    set x1 [expr {$x1 + $sites * [$site getWidth] / double($dbu)}]
    set y1 [expr {$y1 + $rows * [$site getHeight] / double($dbu)}]
    return [list $x0 $y0 $x1 $y1]
}

proc est_find_site { name } {
    foreach lib [[ord::get_db] getLibs] {
        set site [$lib findSite $name]
        if {$site ne "NULL"} {
            return $site
        }
    }
    error "EST-perturb: site $name not found in any library"
}

# The density nudge: +0.001 on the target both the macro placer and
# global placement derive their density from.  A thousandth is far below
# anything a person would set deliberately -- PLACE_DENSITY here is 0.65
# -- and it is the knob AutoTuner tunes, so it is the tuning-surface
# analogue of a seed.
proc est_place_density { } {
    set eps [est_flag PLACE_DENSITY_EPS 0]
    return [expr {[place_density_with_lb_addon] + $eps}]
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

# 1. Floorplan.  A stage like any other rather than a preamble: the
# batch walk needs it inside the tree so a configuration that perturbs
# the core rectangle can fork here and share the load with its siblings.
# Every current manifest agrees on its knobs, so the walk's sole-subtree
# path runs it inline and nothing forks -- identical to when this lived
# in estimator.tcl.
proc est_stage_floorplan { } {
    est_perturb_clock floorplan
    time_phase floorplan {
        initialize_floorplan -die_area $::env(DIE_AREA) \
            -core_area [est_core_area] \
            -site $::env(PLACE_SITE)

        if {$::env(MAKE_TRACKS) ne ""} {
            # At global scope, as it was when this ran from estimator.tcl's
            # top level: the platform's make_tracks script is not written
            # to be sourced into a proc's local frame.
            uplevel #0 [list source $::env(MAKE_TRACKS)]
        }
    }
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
    est_perturb_clock pins_pre
    if {[est_flag PLACE_IOS 0] != 1} {
        time_phase place_pins { est_place_pins }
    }
}

# 4. Macro Placement (mirrors ORFS macro_place_util.tcl).  Gated: with
# macros present this is not free, and leaving it unconditional made the
# "synthesis only" rung silently include a full RTLMP run.
proc est_stage_macro_place { } {
    est_perturb_clock macro_place
    if {[est_flag RUN_MACRO_PLACE 1] == 1 && [find_macros] != ""} {
        time_phase macro_place {
            lassign $::env(MACRO_PLACE_HALO) halo_x halo_y
            set mp_args [list -halo_width $halo_x -halo_height $halo_y \
                -target_util [est_place_density]]
            eval rtl_macro_placer $mp_args [est_args RTLMP_ARGS]
        }
    }
}

# 5. Global Placement
proc est_stage_global_place { } {
    est_perturb_clock global_place
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
            set gp_args "-density [est_place_density]"
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

            # Recorded into the leaf JSON, not just the log: a knob
            # that silently fails to reach the tool looks exactly like a
            # knob that does nothing, and the two need telling apart.
            set ::est_gp_args $gp_args
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
    est_perturb_clock clock
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
    est_perturb_clock repair_design
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
    est_perturb_clock grt
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
    set ::missing_paths 0
    set ::sampled_paths [llength $target_paths]
    foreach pt $target_paths {
        set start [lindex $pt 0]
        set end [lindex $pt 1]
        set paths [find_timing_paths -sort_by_slack -group_path_count 1 -from $start -to $end]

        if {[llength $paths] == 0} {
            # Default is a hard error, and deliberately so: dropping the
            # paths a configuration cannot find would let it quietly
            # discard the awkward ones and look good doing it.
            #
            # ALLOW_MISSING_PATHS exists for the one case where a missing
            # path is the measurement rather than a fault -- the
            # seed-sensitivity study's synthesis arm, where the netlist
            # was re-synthesised against a nudged constraint and the cells
            # a path ran through may genuinely no longer exist.  There the
            # survival rate is the headline number, so a miss is counted
            # and reported instead of aborting the run.
            if {[est_flag ALLOW_MISSING_PATHS 0] == 1} {
                incr ::missing_paths
                continue
            }
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

# Where the macros ended up.
#
# The timing consequence of a macro move is a lagging indicator, and it
# depends on the estimator's timing model being right. The placement
# itself does not: if a one-site nudge to the core relocates macros by
# tens of microns, macro placement is chaotic and no amount of care
# downstream repairs that. So the origins are recorded directly and
# compared between runs.
#
# This matters here more than it did on the wire-only design.
# rtl_macro_placer has no seed to vary -- checked against the OpenROAD mpl
# documentation, there is no -seed and no -num_runs -- so a perturbation
# is the only way to probe it, exactly as for the rest of this study.
proc est_macro_origins { } {
    set blk [ord::get_db_block]
    set out {}
    foreach inst [$blk getInsts] {
        if { ![[$inst getMaster] isBlock] } {
            continue
        }
        lassign [$inst getOrigin] x y
        lappend out [list [$inst getName] $x $y [$inst getOrient]]
    }
    return [lsort -index 0 $out]
}

proc est_write_json { out_json load_s estimate_s sta_s } {
    set total_s [expr {$load_s + $estimate_s + $sta_s}]
    set out_fp [open $out_json w]
    puts $out_fp "{"
    puts $out_fp "\"runtime_s\": $total_s,"
    # Always emitted, so a reader never has to guess whether a short
    # path list means a tolerant run or a small sample.
    if {[info exists ::est_gp_args]} {
        puts $out_fp "\"gp_args\": \"[string map {\" \\\"} $::est_gp_args]\","
    }
    # Macro origins in database units, sorted by instance name so two
    # runs are directly comparable. Empty on a design with no macros.
    set dbu [[[ord::get_db] getTech] getDbUnitsPerMicron]
    puts $out_fp "\"dbu_per_micron\": $dbu,"
    puts $out_fp "\"macros\": \{"
    set macro_first 1
    foreach m [est_macro_origins] {
        lassign $m mname mx my morient
        if {$macro_first == 0} { puts $out_fp "," }
        set macro_first 0
        # ODB escapes Verilog identifiers, so a macro instance is named
        # gen_i\[0\].gen_j\[0\].u_mac -- and a backslash-bracket is not a
        # valid JSON escape. Escape it the same way est_log_edge does.
        set safe [string map {\\ \\\\ \" \\\"} $mname]
        puts -nonewline $out_fp "  \"$safe\": \[$mx, $my, \"$morient\"\]"
    }
    puts $out_fp ""
    puts $out_fp "\},"
    puts $out_fp "\"sampled_paths\": $::sampled_paths,"
    puts $out_fp "\"missing_paths\": $::missing_paths,"
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
