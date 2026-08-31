# Measured selection over a seed-generated population of macro
# placements: the selector the macro_score audit argued for
# (ideas/rtl-mpl.md).
#
# RTL-MP's annealing cost picks the better of two placements at roughly
# coin-flip probability, so instead of trusting the objective this walk
# generates k candidates with rtl_macro_placer -random_seed (carried
# OpenROAD patch), scores each with a fast non-timing-driven global
# placement -- a measurement taken on the far side of the fog that
# implicitly prices density and congestion -- and materializes the
# winner's placement as macro.tcl for the production flow variant to
# consume through MACRO_PLACEMENT_TCL.
#
# The walk runs off the synthesis output (orfs_run src = <design>_synth)
# and shares one production floorplan spine; candidates diverge only at
# macro_place, so the //fork copy-on-write snapshot pays for the whole
# shared prefix.  Two execution shapes, selected by MS_SERIAL_THREADS:
#
#   0 (default)  fork -jobs $MS_JOBS: candidates run in parallel,
#                single-threaded each (fork quiesces set_thread_count;
#                a child must not raise it).
#   N > 0        no fork: candidates run sequentially in the parent
#                with set_thread_count N.  Exists for the parallelism
#                calibration experiment: global placement saturates on
#                internal parallelism well below the core count, and
#                the winning shape is decided by measurement, not
#                folklore (see README, "Parallelism calibration").
#
# Each candidate leaf writes <tag>.json (score components, runtimes,
# peak RSS) and <tag>.place.tcl (the production 2_2_floorplan_macro.tcl
# ORFS already dumps) into the evidence directory; the parent joins,
# selects by MS_SELECT_KPI and copies the winner to the declared
# macro.tcl output.
#
# Faithfulness rests on the carried OpenROAD patches: -random_seed makes
# a candidate reproducible, snap-inside-core makes its place.tcl
# round-trip through place_macro, and the all-fixed standard-cell
# seeding makes the consumer variant's injection equivalent to the
# generation run.  Selection therefore ships coordinates, not a recipe.

source $::env(ORFS_FORK_TCL)
source $::env(EXTRACT_LIB_TCL)

proc ms_env { name default } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

# Evidence directory: MS_OUT_DIR (driver-owned, orfs_run_executable) or
# RUN_OUTPUT_DIR (tree artifact, orfs_run out_dir).
set ::ms_out [ms_env MS_OUT_DIR [ms_env RUN_OUTPUT_DIR ""]]
if { $::ms_out eq "" } {
    error "macro_select: set MS_OUT_DIR or declare out_dir"
}
set ::ms_work [ms_env MS_WORK [file join $::env(WORK_HOME) macro_select_work]]
# Defaults calibrated on the campaign machine class (24C/48T, 64GB
# Threadripper; README "Parallelism calibration"): fork -jobs 12 is the
# throughput knee at 65 candidates/hour -- jobs 24 buys 1% for double
# the per-child latency, and the serial multi-threaded shape is 3x
# slower because global placement saturates on internal parallelism.
# 24 candidates therefore cost ~22 minutes.
set ::ms_k [ms_env MS_K 24]
set ::ms_jobs [ms_env MS_JOBS 12]
set ::ms_serial_threads [ms_env MS_SERIAL_THREADS 0]
# Default selection KPI: the macro-path aggregate. The E1 campaign
# measured period at grt as macro-placement-insensitive at this
# utilization (every candidate inside delta_tie) while the macro-path
# mean spans ~300ps and is ranked by this proxy at rho +0.72; at tight
# utilization macro paths become the period, so the KPI is
# regime-robust (see ideas/rtl-mpl.md and score_vs_flow_swerv.json).
set ::ms_kpi [ms_env MS_SELECT_KPI macro_mean]
set ::ms_macro_tcl [ms_env MS_MACRO_TCL [file join $::env(WORK_HOME) macro.tcl]]
set ::ms_fork_opts [list -timeout [ms_env MS_CHILD_TIMEOUT 14400]]
file mkdir $::ms_out

set ::env(KEEP_VARS) 1
set ::env(SKIP_REPORT_METRICS) 1

proc ms_redirect { tag } {
    set base [file join $::ms_work $tag]
    foreach {var sub} {RESULTS_DIR results REPORTS_DIR reports
                       LOG_DIR logs OBJECTS_DIR objects} {
        set dir [file join $base $sub]
        file mkdir $dir
        set ::env($var) $dir
    }
    return $base
}

set ::ms_tail_s 0.0
proc ms_step { script } {
    set t0 [clock clicks -milliseconds]
    uplevel #0 [list source [file join $::env(SCRIPTS_DIR) $script]]
    set s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]
    set ::ms_tail_s [expr {$::ms_tail_s + $s}]
    puts "macro_select: $script done in ${s}s"
    return $s
}

proc ms_vmhwm_kb { } {
    if { [catch {
        set fp [open /proc/self/status r]
        set status [read $fp]
        close $fp
        regexp {VmHWM:\s+(\d+) kB} $status -> kb
    }] } {
        return 0
    }
    return $kb
}

# Append -random_seed to the exact argument list ORFS's
# macro_place_util.tcl constructs.  RTLMP_ARGS would REPLACE that list,
# dropping halos and target_util; wrapping the command keeps ORFS's
# arguments and adds only the seed.
proc ms_wrap_placer_seed { seed } {
    if { [info commands ms_real_rtl_macro_placer] eq "" } {
        rename rtl_macro_placer ms_real_rtl_macro_placer
        proc rtl_macro_placer { args } {
            ms_real_rtl_macro_placer {*}$args -random_seed $::ms_seed
        }
    }
    set ::ms_seed $seed
}

# The fast non-timing-driven scoring rung (the estimation ladder's gate
# rung): pins once, one global placement with timing/routability off,
# placement parasitics, the shared sampling instrument.
proc ms_score_candidate { } {
    set t0 [clock clicks -milliseconds]
    if { ![info exists ::ms_pins_placed] } {
        if { [info exists ::env(IO_CONSTRAINTS)] && $::env(IO_CONSTRAINTS) ne "" } {
            uplevel #0 [list source $::env(IO_CONSTRAINTS)]
        }
        place_pins -hor_layers $::env(IO_PLACER_H) \
            -ver_layers $::env(IO_PLACER_V)
        set ::ms_pins_placed 1
    }
    set gp_args "-density [place_density_with_lb_addon]"
    set cell_pad [ms_env CELL_PAD_IN_SITES_GLOBAL_PLACEMENT 0]
    append gp_args " -pad_left $cell_pad -pad_right $cell_pad"
    append gp_args " -force_center_initial_place"
    eval global_placement $gp_args
    set gpl_s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]

    set t0 [clock clicks -milliseconds]
    estimate_parasitics -placement
    set_propagated_clock [all_clocks]
    set sample [extract_sample_paths]
    set sta_s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]

    set wq25_sum 0.0
    set wq25_n 0
    set macro_sum 0.0
    set macro_n 0
    foreach pt [dict get $sample paths] {
        set period [lindex $pt 2]
        if { [lindex $pt 3] } {
            set macro_sum [expr {$macro_sum + $period}]
            incr macro_n
        } else {
            set wq25_sum [expr {$wq25_sum + $period}]
            incr wq25_n
        }
    }
    set wq25 [expr {$wq25_n ? $wq25_sum / $wq25_n : 0.0}]
    set macro_mean [expr {$macro_n ? $macro_sum / $macro_n : 0.0}]

    return [dict create \
        clock_period [dict get $sample clock_period] \
        wns [dict get $sample wns] \
        period [expr {[dict get $sample clock_period] - [dict get $sample wns]}] \
        wq25 $wq25 \
        macro_mean $macro_mean \
        gpl_s $gpl_s \
        sta_s $sta_s \
        sample $sample]
}

proc ms_leaf { tag seed score place_s } {
    set fp [open [file join $::ms_out ${tag}.json] w]
    puts $fp "{"
    puts $fp "\"tag\": \"$tag\","
    puts $fp "\"seed\": $seed,"
    puts $fp "\"time_unit\": \"[sta::unit_scale_abbreviation time][sta::unit_suffix time]\","
    puts $fp "\"clock_period\": [dict get $score clock_period],"
    puts $fp "\"wns\": [dict get $score wns],"
    puts $fp "\"period\": [dict get $score period],"
    puts $fp "\"wq25\": [dict get $score wq25],"
    puts $fp "\"macro_mean\": [dict get $score macro_mean],"
    puts $fp "\"macro_place_s\": $place_s,"
    puts $fp "\"gpl_s\": [dict get $score gpl_s],"
    puts $fp "\"sta_s\": [dict get $score sta_s],"
    puts $fp "\"vmhwm_kb\": [ms_vmhwm_kb],"
    puts $fp "\"paths\": [extract_paths_json [dict get $score sample paths]]"
    puts $fp "}"
    close $fp
    puts "macro_select: leaf $tag done (macro_place ${place_s}s,\
        gpl [dict get $score gpl_s]s)"
}

# One candidate: seeded production macro placement, then the scoring
# rung.  Runs inside a fork child (parallel shape) or inline in the
# parent (serial calibration shape).
proc ms_candidate { seed } {
    set tag cand_s$seed
    ms_redirect $tag
    ms_wrap_placer_seed $seed
    set t0 [clock clicks -milliseconds]
    ms_step macro_place.tcl
    set place_s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]
    file copy -force \
        [file join $::env(RESULTS_DIR) 2_2_floorplan_macro.tcl] \
        [file join $::ms_out $tag.place.tcl]
    set score [ms_score_candidate]
    ms_leaf $tag $seed $score $place_s
}

# In-parent reset between serial candidates: macros back to unfixed and
# unplaced, standard cells and pins unplaced, macro soft blockages gone.
# Fork children never need this -- each inherits the pristine
# post-floorplan snapshot.
proc ms_reset_placement { } {
    set blk [ord::get_db_block]
    foreach inst [$blk getInsts] {
        set master [$inst getMaster]
        if { [$master isBlock] } {
            $inst setPlacementStatus NONE
            $inst setOrient R0
            $inst setLocation 0 0
        } elseif { [$inst isPlaced] } {
            $inst setPlacementStatus NONE
        }
    }
    foreach blockage [$blk getBlockages] {
        odb::dbBlockage_destroy $blockage
    }
    foreach bterm [$blk getBTerms] {
        foreach bpin [$bterm getBPins] {
            odb::dbBPin_destroy $bpin
        }
    }
    unset -nocomplain ::ms_pins_placed
    unset_propagated_clock [all_clocks]
}

# ---------------------------------------------------------------------
# The walk.

set seeds {}
for {set i 0} {$i < $::ms_k} {incr i} { lappend seeds $i }
puts "macro_select: [llength $seeds] candidates, kpi $::ms_kpi,\
    [expr {$::ms_serial_threads > 0 ?
        "serial with $::ms_serial_threads threads" :
        "fork -jobs $::ms_jobs"}]"

ms_redirect spine
file copy -force $::env(ODB_FILE) \
    [file join $::env(RESULTS_DIR) 1_synth.odb]
file copy -force [file rootname $::env(ODB_FILE)].sdc \
    [file join $::env(RESULTS_DIR) 1_synth.sdc]
set t0 [clock clicks -milliseconds]
ms_step floorplan.tcl
set ::ms_prefix_s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]

set failed {}
if { $::ms_serial_threads > 0 } {
    set_thread_count $::ms_serial_threads
    foreach seed $seeds {
        if { [catch { ms_candidate $seed } err] } {
            puts stderr "macro_select: candidate s$seed failed: $err"
            lappend failed s$seed
        }
        ms_reset_placement
    }
} else {
    set statuses [fork -jobs $::ms_jobs {*}$::ms_fork_opts seed $seeds {
        ms_candidate $seed
    }]
    dict for {seed code} $statuses {
        if {$code != 0} {
            puts stderr "macro_select: candidate s$seed failed with\
                status $code; its outputs are missing"
            lappend failed s$seed
        }
    }
}

# ---------------------------------------------------------------------
# Join and select.

proc ms_read_json_number { path key } {
    set fp [open $path r]
    set content [read $fp]
    close $fp
    if { ![regexp "\"$key\":\\s*(\[-0-9.eE\]+)" $content -> value] } {
        error "macro_select: no $key in $path"
    }
    return $value
}

set best_tag ""
set best_score Inf
set scored 0
foreach seed $seeds {
    set tag cand_s$seed
    set json [file join $::ms_out $tag.json]
    if { ![file exists $json] } { continue }
    set score [ms_read_json_number $json $::ms_kpi]
    incr scored
    puts "macro_select: $tag $::ms_kpi = $score"
    if { $score < $best_score } {
        set best_score $score
        set best_tag $tag
    }
}
if { $best_tag eq "" } {
    error "macro_select: no candidate produced a score"
}

file copy -force [file join $::ms_out $best_tag.place.tcl] $::ms_macro_tcl
set fp [open [file join $::ms_out winner.json] w]
puts $fp "{\"winner\": \"$best_tag\", \"kpi\": \"$::ms_kpi\",\
 \"score\": $best_score, \"scored\": $scored,\
 \"candidates\": [llength $seeds], \"prefix_s\": $::ms_prefix_s}"
close $fp
puts "macro_select: winner $best_tag ($::ms_kpi = $best_score,\
    $scored/[llength $seeds] scored)"
exit 0
