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
# than a wall-clock difference, and load_s/floorplan were measured once
# in the root for everyone.

source $::env(ORFS_FORK_TCL)

# Sequential is the default: one active run owns the whole machine, which
# is what honest runtime numbers need.  EST_PARALLEL=1 forks the divergent
# subtrees concurrently instead -- shared edges are still paid once, but
# siblings contend for the machine, so it is for callers that never look
# at the runtime axis (the CI machinery test) and for accuracy-only
# sweeps.
set ::est_fork_opts {}
if {[info exists ::env(EST_PARALLEL)] && $::env(EST_PARALLEL) eq "1"} {
    lappend ::est_fork_opts -parallel
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
set ::est_stage_names {
    wire_rc
    pins_pre
    macro_place
    global_place
    clock
    repair_design
    grt
    repair_timing
}
set ::est_stage_knobs [dict create \
    wire_rc {WIRE_RC_LAYER_OVERRIDE} \
    pins_pre {PLACE_IOS} \
    macro_place {RUN_MACRO_PLACE RTLMP_ARGS} \
    global_place {RUN_PLACE GPL_TIMING_DRIVEN GPL_ROUTABILITY_DRIVEN \
                  GPL_VIRTUAL_CTS GP_ARGS CELL_PAD_IN_SITES_GLOBAL_PLACEMENT} \
    clock {CLOCK_MODE CTS_DPL CTS_ARGS_EXTRA} \
    repair_design {RUN_REPAIR_DESIGN REPAIR_DESIGN_ARGS} \
    grt {RUN_GRT GRT_ITERATIONS GRT_ARGS} \
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
proc est_log_edge { stage seconds } {
    set path [string map {\\ \\\\ \" \\\"} [join $::est_path " > "]]
    set fp [open [file join $::env(EST_RESULTS_DIR) edges.jsonl] a]
    puts $fp "{\"path\": \"$path\", \"stage\": \"$stage\", \"seconds\": $seconds}"
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
est_log_edge floorplan [dict get $::phase_times floorplan]
est_walk $est_configs 0
puts "estimator batch: walk complete"
