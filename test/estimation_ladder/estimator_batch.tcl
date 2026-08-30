# Batch mode: one estimator process walks a decision tree of
# configurations instead of paying the shared prefix once per trial.
#
# The manifest is a directory of <id>.cfg files, one KEY=VALUE line per
# knob (the same knob names the single-config mode reads from the
# environment).  The knob space is a tree because the stage order is
# fixed: configurations are grouped stage by stage on the knobs that
# stage consumes, and where a stage has more than one distinct setting
# the walk forks -- a copy-on-write snapshot per group, sequential
# depth-first, so every tree edge (stage execution) runs exactly once
# and a crashed configuration loses only its own subtree (its leaf JSON
# is simply missing; siblings still land).  See docs/fork.md.
#
# Each leaf writes EST_RESULTS_DIR/<id>.json in the same schema as the
# single-config OUTPUT_JSON, with two caveats inherent to sharing:
# estimate_s is the sum of the timed phases on the leaf's own root path
# (fork inherits ::phase_times, so that attribution is exact) rather
# than a wall-clock difference, and load_s was measured once in the root
# for everyone.

source $::env(ORFS_FORK_TCL)

# Sequential is the default: one active run owns the whole machine, which
# is what honest runtime numbers need.  EST_PARALLEL=1 runs the divergent
# subtrees concurrently instead -- shared edges are still paid once, but
# siblings contend, so it is for callers that never look at the runtime
# axis (the CI machinery test) and for accuracy-only sweeps.
#
# -jobs, not -parallel: -parallel forks every child at once, so a wide
# walk oversubscribes badly -- a 41-leaf wave put 41 OpenROAD processes on
# 16 cores.  -jobs runs a bounded pool, one tool process per core, the way
# a build tool schedules.  How many is the infrastructure's decision
# (ORFS_FORK_JOBS, else nproc), so this file states no policy; see
# docs/fork.md.  The walk never rendezvouses across siblings -- leaves are
# independent -- so the guarantee -parallel buys is one this study does
# not need.
set ::est_fork_opts {}
if {[info exists ::env(EST_PARALLEL)] && $::env(EST_PARALLEL) eq "1"} {
    lappend ::est_fork_opts -jobs default
}

# The per-subtree budget stands in for the per-trial timeout of the
# one-process-per-trial mode: a runaway subtree self-destructs (status
# 142, its leaf JSONs missing) instead of stalling the walk or, in
# parallel mode, outliving the whole batch's deadline.
if {[info exists ::env(EST_SUBTREE_TIMEOUT)] && $::env(EST_SUBTREE_TIMEOUT) ne ""} {
    lappend ::est_fork_opts -timeout $::env(EST_SUBTREE_TIMEOUT)
}

# Which stage consumes which knobs, in flow order.  A knob shared by two
# stages is keyed at the earliest stage that reads it (PLACE_IOS branches
# pin placement, and global placement then re-reads the inherited value).
#
# TRAP, for anyone writing a manifest: leaving a knob OUT of a .cfg does
# not turn it off.  est_flag falls back to the environment, and some of
# these are real ORFS variables the flow sets itself --
# GPL_TIMING_DRIVEN and GPL_ROUTABILITY_DRIVEN default to 1.  An omitted
# knob therefore means "whatever ORFS decided", so a study comparing a
# configuration with a feature against one without it must state the zero
# explicitly in both.  This has bitten once already: a rung table that
# omitted them ran every rung with the same timing-driven placement and
# reported four identical columns.  Leaf JSONs record gp_args so the same
# mistake shows up as evidence instead of as a puzzle.
set ::est_stage_names {
    floorplan
    wire_rc
    pins_pre
    macro_place
    global_place
    clock
    repair_design
    grt
    repair_timing
}
# The CLK_PERIOD_EPS_<STAGE> knobs are what make the seed-sensitivity
# study cheap, and registering each against its own stage is the whole
# mechanism: a configuration differing from the spine only in, say,
# CLK_PERIOD_EPS_GRT groups identically with it at every earlier stage, so
# the walk shares the entire prefix and forks only at grt.  Perturbing a
# late stage therefore costs only that stage's tail.  One global knob
# would differ at depth 0 and re-run everything.
set ::est_stage_knobs [dict create \
    floorplan {CORE_AREA_EPS_SITES CORE_AREA_EPS_ROWS \
               CLK_PERIOD_EPS_FLOORPLAN} \
    wire_rc {WIRE_RC_LAYER_OVERRIDE} \
    pins_pre {PLACE_IOS CLK_PERIOD_EPS_PINS_PRE} \
    macro_place {RUN_MACRO_PLACE RTLMP_ARGS PLACE_DENSITY_EPS \
                 CLK_PERIOD_EPS_MACRO_PLACE} \
    global_place {RUN_PLACE GPL_TIMING_DRIVEN GPL_ROUTABILITY_DRIVEN \
                  GPL_VIRTUAL_CTS GP_ARGS CELL_PAD_IN_SITES_GLOBAL_PLACEMENT \
                  CLK_PERIOD_EPS_GLOBAL_PLACE} \
    clock {CLOCK_MODE CTS_DPL CTS_ARGS_EXTRA CLK_PERIOD_EPS_CLOCK} \
    repair_design {RUN_REPAIR_DESIGN REPAIR_DESIGN_ARGS \
                   CLK_PERIOD_EPS_REPAIR_DESIGN} \
    grt {RUN_GRT GRT_ITERATIONS GRT_ARGS CLK_PERIOD_EPS_GRT} \
    repair_timing {RUN_REPAIR_TIMING REPAIR_TIMING_ARGS} \
]

proc est_read_manifest { dir } {
    set configs [dict create]
    foreach f [lsort [glob -nocomplain -directory $dir *.cfg]] {
        set id [file rootname [file tail $f]]
        set cfg [dict create]
        set fp [open $f r]
        foreach line [split [read $fp] "\n"] {
            set line [string trim $line]
            if {$line eq "" || [string index $line 0] eq "#"} {
                continue
            }
            set idx [string first "=" $line]
            if {$idx < 1} {
                error "manifest $f: not KEY=VALUE: $line"
            }
            dict set cfg [string range $line 0 [expr {$idx - 1}]] \
                [string range $line [expr {$idx + 1}] end]
        }
        close $fp
        dict set configs $id $cfg
    }
    return $configs
}

# The grouping key distinguishes "knob unset" (est_flag default applies)
# from any explicit value, including the empty string.
proc est_stage_key { cfg knobs } {
    set key {}
    foreach k $knobs {
        if {[dict exists $cfg $k]} {
            lappend key "$k=[dict get $cfg $k]"
        } else {
            lappend key "$k?"
        }
    }
    return $key
}

# Edge log: one JSON line per executed tree edge, appended as it
# completes (children inherit ::est_path across fork, so the path is the
# edge's identity in the trie). This is the instrumentation behind the
# resident-root / snapshot-cache decision: wave_savings.py sums, across a
# study's waves, the time spent re-computing edges an earlier wave had
# already paid for -- the upper bound on what keeping snapshots alive
# between waves would save.
# Memory, for provisioning an ensemble.
#
# An ensemble's size is bounded by cores AND by memory, and the memory
# bound cannot be guessed: fork children are copy-on-write, so k children
# do NOT cost k times a run.  Shared pages are paid once however many
# children there are; what each additional child really costs is the pages
# it has dirtied since the fork.  That is Private_Dirty, so it is what
# gets logged -- VmHWM alongside it, but VmHWM is inherited across fork
# and so describes the lineage's peak rather than this child's marginal
# cost.  Sizing a wave from VmHWM would badly under-provision.
#
# Read from smaps_rollup in one go; absent on non-Linux, where fork is
# unsupported anyway (docs/fork.md).
proc est_mem_kb { } {
    set out [dict create private_dirty_kb -1 peak_kb -1]
    if { [file exists /proc/self/smaps_rollup] } {
        set fp [open /proc/self/smaps_rollup r]
        set data [read $fp]
        close $fp
        if { [regexp {Private_Dirty:\s+(\d+) kB} $data -> kb] } {
            dict set out private_dirty_kb $kb
        }
    }
    if { [file exists /proc/self/status] } {
        set fp [open /proc/self/status r]
        set data [read $fp]
        close $fp
        if { [regexp {VmHWM:\s+(\d+) kB} $data -> kb] } {
            dict set out peak_kb $kb
        }
    }
    return $out
}

proc est_log_edge { stage seconds } {
    set path [string map {\\ \\\\ \" \\\"} [join $::est_path " > "]]
    set mem [est_mem_kb]
    set fp [open [file join $::env(EST_RESULTS_DIR) edges.jsonl] a]
    puts $fp "{\"path\": \"$path\", \"stage\": \"$stage\",\
        \"seconds\": $seconds,\
        \"private_dirty_kb\": [dict get $mem private_dirty_kb],\
        \"peak_kb\": [dict get $mem peak_kb]}"
    close $fp
}

proc est_apply_stage { stage knobs key cfg } {
    foreach k $knobs {
        if {[dict exists $cfg $k]} {
            dict set ::est_cfg $k [dict get $cfg $k]
        }
    }
    lappend ::est_path $key
    set t0 [clock clicks -milliseconds]
    est_stage_$stage
    est_log_edge $stage [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]
}

# At the bottom of the tree the remaining configurations are identical in
# every stage knob, so one STA pass serves them all; only the leaf-level
# DUMP_FEATURES output option may still differ per id.
proc est_run_leaves { configs } {
    dict set ::phase_times load $::load_s
    est_measure_paths
    set sta_s [dict get $::phase_times sta]
    est_log_edge sta $sta_s
    set estimate_s 0.0
    dict for {name secs} $::phase_times {
        if {$name ni {load sta}} {
            set estimate_s [expr {$estimate_s + $secs}]
        }
    }
    dict for {id cfg} $configs {
        if {[dict exists $cfg DUMP_FEATURES]} {
            dict set ::est_cfg DUMP_FEATURES [dict get $cfg DUMP_FEATURES]
        } else {
            dict unset ::est_cfg DUMP_FEATURES
        }
        est_write_json [file join $::env(EST_RESULTS_DIR) $id.json] \
            $::load_s $estimate_s $sta_s
        puts "estimator batch: leaf $id done\
            (estimate ${estimate_s}s, sta ${sta_s}s)"
    }
}

proc est_walk { configs depth } {
    if {$depth == [llength $::est_stage_names]} {
        est_run_leaves $configs
        return
    }
    set stage [lindex $::est_stage_names $depth]
    set knobs [dict get $::est_stage_knobs $stage]

    set groups [dict create]
    dict for {id cfg} $configs {
        dict set groups [est_stage_key $cfg $knobs] $id $cfg
    }

    if {[dict size $groups] == 1} {
        # Sole subtree: this process is already dedicated to it, so an
        # inline stage costs nothing a fork would buy.
        set key [lindex [dict keys $groups] 0]
        set sub [dict get $groups $key]
        est_apply_stage $stage $knobs $key [lindex [dict values $sub] 0]
        est_walk $sub [expr {$depth + 1}]
        return
    }

    set statuses [fork {*}$::est_fork_opts key [dict keys $groups] {
        set sub [dict get $groups $key]
        est_apply_stage $stage $knobs $key [lindex [dict values $sub] 0]
        est_walk $sub [expr {$depth + 1}]
    }]
    dict for {key code} $statuses {
        if {$code != 0} {
            puts stderr "estimator batch: subtree ($stage: $key)\
                failed with status $code; its leaves are missing"
        }
    }
}

set est_configs [est_read_manifest $::env(EST_MANIFEST_DIR)]
if {[dict size $est_configs] == 0} {
    error "no .cfg files in EST_MANIFEST_DIR=$::env(EST_MANIFEST_DIR)"
}
puts "estimator batch: walking [dict size $est_configs] configurations"
set ::est_path {}
est_log_edge load $::load_s
est_walk $est_configs 0
puts "estimator batch: walk complete"
