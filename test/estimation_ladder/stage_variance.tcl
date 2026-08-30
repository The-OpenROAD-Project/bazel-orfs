# Flow-side per-stage variance decomposition: where in the production
# flow is the noise born?
#
# seed_sensitivity.py measures sigma_E -- the ESTIMATOR's per-stage
# stability -- and is explicit that the flow-side dispersion sigma_T is
# out of its scope.  This walk is that flow-side arm.  It runs the real
# ORFS stage scripts floorplan..grt in ONE OpenROAD process (the
# KEEP_VARS=1 + sequential-source chaining that ORFS's own
# floorplan_to_place.tcl demonstrates; load_design no-ops on an
# in-memory design, so the chain never round-trips through files) and
# uses fork (docs/fork.md) to hang an ensemble off each stage boundary:
#
#   floorplan ... pdn --+-- [place arm]  GPL_RANDOM_SEED x k, tail place..grt
#                       +-- [all arm]    GPL seed + clock nudge + GRT seed, same tail
#     spine place ------+-- [cts arm]    clock nudge x k, tail cts..grt
#       spine cts ------+-- [grt arm]    GRT_SEED x k, tail grt
#         spine grt ----+-- the spine leaf, the unperturbed reference
#
# Every leaf runs the production tail to grt and is measured there by
# extract_lib.tcl -- the same instrument as the ground truth -- so all
# arms are compared at the same point in the flow, in the same KPI, and a
# stage's spread includes whatever the stages after it amplify it into.
#
# The perturbations, per arm:
#  - place: GPL_RANDOM_SEED, the native randomness hook global_place.tcl
#    exposes ("Useful for perturbation studies", variables.yaml) -- a
#    genuine draw from the placer's distribution.
#  - grt: GRT_SEED, ditto for set_global_routing_random.
#  - cts: CTS exposes no seed, so it gets the literature's substitute
#    (Jeong & Kahng's 1ps constraint probe, the same nudge
#    seed_sensitivity.py uses): the clock period moves by eps.  Because
#    min_period = clk_period - slack, the nudge cancels exactly in the
#    KPI; whatever survives is a timing-driven decision inside cts..grt
#    taking a different branch, i.e. tool noise.
#  - all: all three at once -- the directly measured sigma_total that the
#    per-arm decomposition must predict (sum of variances, under
#    independence).  Disagreement is the interaction term the per-stage
#    measurement cannot see, and computing it is the study's validity
#    check.
# Each arm also carries a "null" child with no perturbation at all: a
# deterministic tool must reproduce the spine leaf exactly, so the nulls
# are the harness's free self-test, and a nudge is read back and errors
# if it did not land (a silently inert perturbation would report zero
# noise everywhere -- the one wrong answer that looks clean).
#
# Driven by stage_variance.py; every knob arrives as an env variable so
# the driver owns the ensemble design.  Leaves land as
# SV_OUT_DIR/<arm>_<tag>.json plus walk.json for the spine metadata.

source $::env(ORFS_FORK_TCL)
source $::env(EXTRACT_LIB_TCL)

proc sv_env { name default } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

# Everything the walk writes goes to caller-supplied absolute paths: the
# staged flow outputs under the original RESULTS_DIR are read-only (the
# orfs_run_executable contract), and concurrent leaves must not share
# output directories.
set ::sv_out $::env(SV_OUT_DIR)
set ::sv_work $::env(SV_WORK)
file mkdir $::sv_out

set ::sv_grt_seeds [sv_env SV_GRT_SEEDS "1 2 3 4 5 6 7 8"]
# GPL seeds start at 2: global_placement's initial-place perturbation
# defaults to -random_seed 1, so seed 1 IS the spine's own draw --
# measured bit-identical -- and a member running it would be a second
# null, not a sample.
set ::sv_gpl_seeds [sv_env SV_GPL_SEEDS "2 3 4 5 6 7 8 9"]
set ::sv_cts_eps [sv_env SV_CTS_EPS "-4 -3 -2 -1 1 2 3 4"]
set ::sv_all_k [sv_env SV_ALL_K 8]
set ::sv_fork_opts [list -jobs default -timeout [sv_env SV_CHILD_TIMEOUT 10800]]
set ::sv_keep_work [sv_env SV_KEEP_WORK 0]

# Keep variables across the sourced stage scripts (what ORFS's own
# floorplan_to_place.tcl sets) and skip the per-substep report files:
# the leaves are measured by extract_lib, not by reports nobody reads.
set ::env(KEEP_VARS) 1
set ::env(SKIP_REPORT_METRICS) 1

# Point the ORFS output dirs at a private location.  Called once for the
# spine and again in every forked child before it sources a stage script,
# because the scripts write results/reports as they go.
proc sv_redirect { tag } {
    set base [file join $::sv_work $tag]
    foreach {var sub} {RESULTS_DIR results REPORTS_DIR reports
                       LOG_DIR logs OBJECTS_DIR objects} {
        set dir [file join $base $sub]
        file mkdir $dir
        set ::env($var) $dir
    }
    return $base
}

# Source one production stage script, timed.  The spine accumulates
# prefix seconds (inherited by children at fork); a child accumulates its
# own tail separately so a leaf can report the marginal cost of re-running
# it -- the c in the ensemble budget c * k / p.
set ::sv_prefix_s 0.0
set ::sv_tail_s 0.0
set ::sv_in_child 0
set ::sv_steps [dict create]
proc sv_step { script } {
    set t0 [clock clicks -milliseconds]
    uplevel #0 [list source [file join $::env(SCRIPTS_DIR) $script]]
    set s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]
    dict set ::sv_steps $script $s
    if { $::sv_in_child } {
        set ::sv_tail_s [expr {$::sv_tail_s + $s}]
    } else {
        set ::sv_prefix_s [expr {$::sv_prefix_s + $s}]
    }
    puts "stage_variance: $script done in ${s}s"
    return $s
}

# The clock-period nudge, in SDC time units (ps on asap7), read back and
# verified exactly as est_perturb_clock does -- see estimator_lib.tcl for
# why the tolerance is relative (float32 keeps the period) and why a
# nudge that did not land must be an error rather than a quiet zero.
proc sv_perturb_clock { eps } {
    if { $eps eq "null" || $eps == 0 } {
        return
    }
    set clocks [all_clocks]
    if { [llength $clocks] == 0 } {
        error "stage_variance: clock nudge requested but the design has no clocks"
    }
    set wanted [dict create]
    foreach clk $clocks {
        set name [get_name $clk]
        set want [expr {[get_property $clk period] + $eps}]
        set sources [get_property $clk sources]
        if { [llength $sources] == 0 } {
            error "stage_variance: clock $name reports no sources, so its\
                period cannot be re-issued"
        }
        create_clock -name $name -period $want $sources
        dict set wanted $name $want
    }
    dict for {name want} $wanted {
        set got [get_property [get_clocks $name] period]
        if { abs($got - $want) > 1e-6 * abs($want) } {
            error "stage_variance: clock $name period is $got after asking\
                for $want; the perturbation did not take effect"
        }
    }
}

# Measure the current (post-global_route) design and write the leaf.
# Re-issuing set_propagated_clock and the parasitics estimate keeps the
# measurement conditions bit-identical to extract.tcl's, whatever the
# tail last left behind.
proc sv_leaf { arm tag } {
    set t0 [clock clicks -milliseconds]
    set_propagated_clock [all_clocks]
    estimate_parasitics -global_routing
    set sample [extract_sample_paths]
    set area [extract_design_area]
    set sta_s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]

    set fp [open [file join $::sv_out ${arm}_${tag}.json] w]
    puts $fp "{"
    puts $fp "\"arm\": \"$arm\","
    puts $fp "\"tag\": \"$tag\","
    puts $fp "\"time_unit\": \"[sta::unit_scale_abbreviation time][sta::unit_suffix time]\","
    puts $fp "\"clock_period\": [dict get $sample clock_period],"
    puts $fp "\"wns\": [dict get $sample wns],"
    puts $fp "\"prefix_s\": $::sv_prefix_s,"
    puts $fp "\"tail_s\": $::sv_tail_s,"
    puts $fp "\"sta_s\": $sta_s,"
    set steps {}
    dict for {k v} $::sv_steps { lappend steps "\"$k\": $v" }
    puts $fp "\"steps\": {[join $steps ", "]},"
    puts $fp "[extract_ppa_json $area],"
    puts $fp "\"paths\": [extract_paths_json [dict get $sample paths]]"
    puts $fp "}"
    close $fp
    puts "stage_variance: leaf ${arm}_${tag} done (tail ${::sv_tail_s}s, sta ${sta_s}s)"
}

# A forked ensemble member: redirect the output dirs, apply the arm's
# perturbation, run the tail, measure, and (unless kept for debugging)
# delete the member's working tree -- the leaf JSON is the only product,
# and eight concurrent members' worth of ODB snapshots is real disk.
proc sv_member { arm tag perturb tail } {
    set ::sv_in_child 1
    set base [sv_redirect ${arm}_${tag}]
    uplevel #0 $perturb
    foreach script $tail {
        sv_step $script
    }
    sv_leaf $arm $tag
    if { !$::sv_keep_work } {
        file delete -force $base
    }
}

proc sv_report_statuses { arm statuses } {
    dict for {tag code} $statuses {
        if { $code != 0 } {
            puts stderr "stage_variance: $arm member $tag failed with\
                status $code; its leaf is missing"
        }
    }
}

set FLOORPLAN_STEPS {floorplan.tcl macro_place.tcl tapcell.tcl pdn.tcl}
set PLACE_STEPS {global_place_skip_io.tcl io_placement.tcl global_place.tcl
                 resize.tcl detail_place.tcl}
set CTS_STEPS {cts.tcl}
set GRT_STEPS {global_route.tcl}

# --- spine: floorplan stage on the fixed 1_synth input -----------------
sv_redirect spine
file copy -force $::env(ODB_FILE) [file join $::env(RESULTS_DIR) 1_synth.odb]
file copy -force [file rootname $::env(ODB_FILE)].sdc \
    [file join $::env(RESULTS_DIR) 1_synth.sdc]

foreach script $FLOORPLAN_STEPS { sv_step $script }

# Seed setters as named procs so the fork bodies stay one call each.
proc sv_seed_env { var seed } {
    if { $seed ne "null" } {
        set ::env($var) $seed
    }
}

# The all arm draws its GPL seed from the same list as the place arm on
# purpose: a same-seed pair shares its placement, so the driver can read
# the incremental spread the later levers add on top of an identical
# placement, for free, from the pairing.
proc sv_all_perturb { gpl_seed grt_seed eps } {
    set ::env(GPL_RANDOM_SEED) $gpl_seed
    set ::env(GRT_SEED) $grt_seed
    sv_perturb_clock $eps
}

# --- place arm: fixed floorplan, the placer's own distribution ---------
set tags [concat $::sv_gpl_seeds null]
sv_report_statuses place [fork {*}$::sv_fork_opts tag $tags {
    sv_member place $tag [list sv_seed_env GPL_RANDOM_SEED $tag] \
        [concat $PLACE_STEPS $CTS_STEPS $GRT_STEPS]
}]

# --- all arm: every lever at once, the measured sigma_total ------------
set all_tags {}
for {set i 1} {$i <= $::sv_all_k} {incr i} { lappend all_tags $i }
sv_report_statuses all [fork {*}$::sv_fork_opts tag $all_tags {
    set eps [lindex $::sv_cts_eps [expr {($tag - 1) % [llength $::sv_cts_eps]}]]
    set gpl [lindex $::sv_gpl_seeds \
        [expr {($tag - 1) % [llength $::sv_gpl_seeds]}]]
    sv_member all $tag [list sv_all_perturb $gpl $tag $eps] \
        [concat $PLACE_STEPS $CTS_STEPS $GRT_STEPS]
}]

# --- spine: place stage, unperturbed ------------------------------------
foreach script $PLACE_STEPS { sv_step $script }

# --- cts arm: fixed placement, the constraint nudge ---------------------
set tags [concat $::sv_cts_eps null]
sv_report_statuses cts [fork {*}$::sv_fork_opts tag $tags {
    sv_member cts $tag [list sv_perturb_clock $tag] \
        [concat $CTS_STEPS $GRT_STEPS]
}]

# --- spine: cts, unperturbed --------------------------------------------
foreach script $CTS_STEPS { sv_step $script }

# --- grt arm: fixed clock tree, the router's own distribution -----------
set tags [concat $::sv_grt_seeds null]
sv_report_statuses grt [fork {*}$::sv_fork_opts tag $tags {
    sv_member grt $tag [list sv_seed_env GRT_SEED $tag] $GRT_STEPS
}]

# --- spine: grt, the unperturbed reference leaf --------------------------
foreach script $GRT_STEPS { sv_step $script }
sv_leaf spine base

# Spine metadata: the per-step wall times every budget line starts from.
set fp [open [file join $::sv_out walk.json] w]
puts $fp "{"
set steps {}
dict for {k v} $::sv_steps { lappend steps "\"$k\": $v" }
puts $fp "\"spine_steps\": {[join $steps ", "]},"
puts $fp "\"prefix_s\": $::sv_prefix_s"
puts $fp "}"
close $fp
puts "stage_variance: walk complete"
exit 0
