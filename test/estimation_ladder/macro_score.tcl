# Auditing RTL-MP's scoring function: does the number the macro placer
# optimizes predict what the flow delivers?
#
# stage_variance located the noise: downstream of a fixed macro
# placement this flow is quiet (sigma ~0.7-1.4%), while the placer's
# response to its input swings the achieved period ~25%.  Choosing a
# macro placement therefore IS choosing a downstream outcome -- and
# RTL-MP chooses with its internal annealing cost, which has never been
# checked against downstream timing.  This walk produces, for a
# population of candidate placements spanning winners to deliberately
# degraded, the pair (s, y): RTL-MP's own objective at the placement,
# and the flow's KPI menu at grt.
#
# A finding before the first result: RTL-MP cannot be made to score an
# arbitrary external placement.  There is no evaluate-only entry point;
# the Total Cost it prints is normalized per run, so even its own
# totals are not comparable across runs; and forcing the annealer onto
# a target with per-macro guidance regions fails structurally -- the SA
# explores sequence-pair PACKINGS, and an arbitrary geometry is not in
# that space (measured: 80-247um of non-compliance, including against
# the placer's own winner).  Every score in this audit therefore comes
# from a placement RTL-MP itself produced, with the population widened
# by adversarial FENCES (RTLMP_FENCE_*): confine the macros to a corner
# or strip and the placer emits its best-within-fence placement along
# with the default objective's raw penalty values -- candidates that
# are significantly worse by the placer's own accounting.  Degraded
# permutations of the winner are additionally evaluated on the flow
# side only, explicitly unscored.
#
# Two modes, driven by MS_MODE and orchestrated by macro_score.py
# (the driver owns the population design; each mode reads a manifest
# directory of <tag>.cfg files, KEY=VALUE per line):
#
#   generate  Children fork before floorplan, SEQUENTIALLY (the penalty
#             tables share the run log; MS_TABLE_BEGIN/END markers keep
#             them attributable).  Each child applies its cfg's env
#             overrides -- a CORE_AREA site nudge (winners), one
#             RTLMP_*_WT/halo distortion (tradeoff optima), or an
#             RTLMP_FENCE_* box (adversarially fenced) -- runs
#             floorplan + macro_place under set_debug_level MPL
#             hierarchical_macro_placement 1, and saves the placement
#             (2_2_floorplan_macro.tcl, dumped by ORFS already) plus
#             the macro geometry.  The debug table's RAW values are
#             placement properties, comparable across runs; the driver
#             recombines them into the default objective under one
#             fixed normalization.
#
#   evaluate  One base-floorplan spine; children fork per candidate
#             under -jobs, inject the candidate's true geometry via
#             MACRO_PLACEMENT_TCL (place_macro LOCKs every macro, so
#             rtl_macro_placer logs MPL-0013 and no-ops), verify the
#             injection landed, run the production tail tapcell..grt,
#             and measure the leaf with extract_lib.tcl -- the same
#             instrument as the ground truth and stage_variance.  The
#             spine continues through its own default macro_place to
#             grt: the production reference leaf.  A "null" candidate
#             re-injects the base winner's generation placement, which
#             a deterministic flow must reproduce bit-identically.

source $::env(ORFS_FORK_TCL)
source $::env(EXTRACT_LIB_TCL)

proc ms_env { name default } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

set ::ms_out $::env(MS_OUT_DIR)
set ::ms_work $::env(MS_WORK)
set ::ms_mode $::env(MS_MODE)
set ::ms_manifest $::env(MS_MANIFEST_DIR)
set ::ms_fork_opts [list -timeout [ms_env MS_CHILD_TIMEOUT 10800]]
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
    puts "macro_score: $script done in ${s}s"
    return $s
}

# Same reader as estimator_batch.tcl: a directory of <tag>.cfg files,
# KEY=VALUE per line.
proc ms_read_manifest { dir } {
    set configs [dict create]
    foreach f [lsort [glob -nocomplain -directory $dir *.cfg]] {
        set tag [file rootname [file tail $f]]
        set cfg [dict create]
        set fp [open $f r]
        foreach line [split [read $fp] "\n"] {
            set line [string trim $line]
            if {$line eq "" || [string index $line 0] eq "#"} { continue }
            set idx [string first "=" $line]
            if {$idx < 1} { error "manifest $f: not KEY=VALUE: $line" }
            dict set cfg [string range $line 0 [expr {$idx - 1}]] \
                [string range $line [expr {$idx + 1}] end]
        }
        close $fp
        dict set configs $tag $cfg
    }
    return $configs
}

# The macro geometry as JSON: name, bbox lower-left in microns (what
# place_macro -location takes), size, orientation.  Names are escaped
# because ODB escapes Verilog identifiers.
proc ms_macros_json { } {
    set blk [ord::get_db_block]
    set dbu [expr {double([$blk getDbUnitsPerMicron])}]
    set entries {}
    foreach inst [lsort -command {apply {{a b} {
        string compare [$a getName] [$b getName]
    }}} [$blk getInsts]] {
        if { ![[$inst getMaster] isBlock] } { continue }
        set name [string map {"\\" "\\\\" "\"" "\\\""} [$inst getName]]
        set bbox [$inst getBBox]
        set master [$inst getMaster]
        lappend entries "  \"$name\": {\"x\": [expr {[$bbox xMin] / $dbu}],\
 \"y\": [expr {[$bbox yMin] / $dbu}],\
 \"w\": [expr {[$master getWidth] / $dbu}],\
 \"h\": [expr {[$master getHeight] / $dbu}],\
 \"orient\": \"[$inst getOrient]\",\
 \"placed\": [expr {[$inst isPlaced] ? 1 : 0}]}"
    }
    return "{\n[join $entries ",\n"]\n}"
}

proc ms_write_macros { path } {
    set fp [open $path w]
    puts $fp [ms_macros_json]
    close $fp
}

# Clamp candidate placements into the ACTUAL core box.  RTL-MP places
# against the requested CORE_AREA while the instantiated core rows snap
# slightly smaller, so the placer's own winners can poke a few tens of
# nanometres past the core top -- and place_macro (MPL-34) and
# add_guidance_region (MPL-42) both reject what rtl_macro_placer itself
# produced.  The clamp is bounded by that snap residue (well under the
# 1um landing tolerance); anything larger would be a generator bug and
# is reported.
proc ms_clamp_placements { placements } {
    set blk [ord::get_db_block]
    set dbu [expr {double([$blk getDbUnitsPerMicron])}]
    set core [$blk getCoreArea]
    set lx [expr {[$core xMin] / $dbu}]
    set ly [expr {[$core yMin] / $dbu}]
    set ux [expr {[$core xMax] / $dbu}]
    set uy [expr {[$core yMax] / $dbu}]
    set out {}
    set worst 0.0
    foreach p $placements {
        lassign $p name x y orient
        set inst [$blk findInst $name]
        if {$inst eq "NULL" || $inst eq ""} {
            error "macro_score: macro $name from the candidate file not found"
        }
        set w [expr {[[$inst getMaster] getWidth] / $dbu}]
        set h [expr {[[$inst getMaster] getHeight] / $dbu}]
        set cx [expr {max($lx, min($x, $ux - $w))}]
        set cy [expr {max($ly, min($y, $uy - $h))}]
        set d [expr {max(abs($cx - $x), abs($cy - $y))}]
        if {$d > $worst} { set worst $d }
        lappend out [list $name $cx $cy $orient]
    }
    if {$worst > 0.5} {
        error "macro_score: clamping a candidate into the core moved a\
            macro by ${worst}um; that is a generator bug, not a snap residue"
    }
    return $out
}

proc ms_write_place_file { path placements } {
    set fp [open $path w]
    foreach p $placements {
        lassign $p name x y orient
        puts $fp "place_macro -macro_name {$name} -location\
            {[format %.4f $x] [format %.4f $y]} -orientation $orient"
    }
    close $fp
}

# Parse a place_macro candidate file into {name x y orient} tuples.
proc ms_parse_place_file { path } {
    set fp [open $path r]
    set content [read $fp]
    close $fp
    set out {}
    foreach line [split $content "\n"] {
        if {![regexp {place_macro\s+-macro_name\s+\{(.*)\}\s+-location\s+\{([-0-9.eE]+)\s+([-0-9.eE]+)\}\s+-orientation\s+(\S+)} \
                $line -> name x y orient]} {
            continue
        }
        lappend out [list $name $x $y $orient]
    }
    if {[llength $out] == 0} {
        error "macro_score: no place_macro lines in $path"
    }
    return $out
}

# Max distance (um) between where the candidate asked each macro to be
# and where it actually is -- guidance compliance for score mode, the
# injection-landed guard for evaluate mode.
proc ms_max_displacement { placements } {
    set blk [ord::get_db_block]
    set dbu [expr {double([$blk getDbUnitsPerMicron])}]
    set worst 0.0
    foreach p $placements {
        lassign $p name x y orient
        set inst [$blk findInst $name]
        if {$inst eq "NULL" || $inst eq ""} {
            error "macro_score: macro $name from the candidate file not found"
        }
        set bbox [$inst getBBox]
        set dx [expr {abs([$bbox xMin] / $dbu - $x)}]
        set dy [expr {abs([$bbox yMin] / $dbu - $y)}]
        set d [expr {max($dx, $dy)}]
        if {$d > $worst} { set worst $d }
    }
    return $worst
}

# Measure the post-grt design and write the leaf, same instrument and
# schema as stage_variance so the drivers share their readers.
proc ms_leaf { tag stratum displacement } {
    set t0 [clock clicks -milliseconds]
    set_propagated_clock [all_clocks]
    estimate_parasitics -global_routing
    set sample [extract_sample_paths]
    set area [extract_design_area]
    set sta_s [expr {([clock clicks -milliseconds] - $t0) / 1000.0}]

    set fp [open [file join $::ms_out ${tag}.json] w]
    puts $fp "{"
    puts $fp "\"arm\": \"$stratum\","
    puts $fp "\"tag\": \"$tag\","
    puts $fp "\"time_unit\": \"[sta::unit_scale_abbreviation time][sta::unit_suffix time]\","
    puts $fp "\"clock_period\": [dict get $sample clock_period],"
    puts $fp "\"wns\": [dict get $sample wns],"
    puts $fp "\"displacement_um\": $displacement,"
    puts $fp "\"prefix_s\": $::ms_prefix_s,"
    puts $fp "\"tail_s\": $::ms_tail_s,"
    puts $fp "\"sta_s\": $sta_s,"
    puts $fp "\"macros\": [ms_macros_json],"
    puts $fp "[extract_ppa_json $area],"
    puts $fp "\"paths\": [extract_paths_json [dict get $sample paths]]"
    puts $fp "}"
    close $fp
    puts "macro_score: leaf $tag done (tail ${::ms_tail_s}s)"
}

set FLOORPLAN_ONLY {floorplan.tcl}
set MACRO_STEP {macro_place.tcl}
set EVAL_TAIL {tapcell.tcl pdn.tcl global_place_skip_io.tcl io_placement.tcl
               global_place.tcl resize.tcl detail_place.tcl cts.tcl
               global_route.tcl}

set configs [ms_read_manifest $::ms_manifest]
if {[dict size $configs] == 0} {
    error "macro_score: empty manifest $::ms_manifest"
}
puts "macro_score: mode $::ms_mode, [dict size $configs] entries"

if { $::ms_mode eq "generate" } {
    # Children fork at the root: a winner-stratum cfg nudges CORE_AREA,
    # so nothing before floorplan can be shared.  Sequential, so the
    # debug tables in the shared log stay attributable.
    set statuses [fork {*}$::ms_fork_opts tag [dict keys $configs] {
        ms_redirect gen_$tag
        file copy -force $::env(ODB_FILE) \
            [file join $::env(RESULTS_DIR) 1_synth.odb]
        file copy -force [file rootname $::env(ODB_FILE)].sdc \
            [file join $::env(RESULTS_DIR) 1_synth.sdc]
        dict for {k v} [dict get $configs $tag] {
            if {$k ne "TAG"} { set ::env($k) $v }
        }
        set_debug_level MPL hierarchical_macro_placement 1
        puts "MS_TABLE_BEGIN $tag"
        foreach s $FLOORPLAN_ONLY { ms_step $s }
        foreach s $MACRO_STEP { ms_step $s }
        puts "MS_TABLE_END $tag"
        file copy -force \
            [file join $::env(RESULTS_DIR) 2_2_floorplan_macro.tcl] \
            [file join $::ms_out $tag.place.tcl]
        ms_write_macros [file join $::ms_out $tag.macros.json]
        puts "macro_score: leaf $tag done"
    }]
} elseif { $::ms_mode eq "evaluate" } {
    ms_redirect spine
    file copy -force $::env(ODB_FILE) \
        [file join $::env(RESULTS_DIR) 1_synth.odb]
    file copy -force [file rootname $::env(ODB_FILE)].sdc \
        [file join $::env(RESULTS_DIR) 1_synth.sdc]
    foreach s $FLOORPLAN_ONLY { ms_step $s }
    set ::ms_prefix_s $::ms_tail_s

    set statuses [fork -jobs default {*}$::ms_fork_opts tag [dict keys $configs] {
        set base [ms_redirect eval_$tag]
        set ::ms_tail_s 0.0
        # Inject the candidate's TRUE geometry (clamped into the actual
        # core, see ms_clamp_placements): y always measures the
        # candidate itself, never the scoring run's approximation of it.
        set placements [ms_clamp_placements [ms_parse_place_file \
            [dict get $configs $tag PLACE_FILE]]]
        set place_file [file join $base injected.tcl]
        ms_write_place_file $place_file $placements
        set ::env(MACRO_PLACEMENT_TCL) $place_file
        foreach s $MACRO_STEP { ms_step $s }
        # The injection-landed guard: a placement that silently failed
        # to land would measure the wrong candidate.  place_macro
        # snapping can shift a location by a track pitch, so the
        # tolerance is 1um -- far below any inter-candidate distance
        # and far above any snap.
        set disp [ms_max_displacement $placements]
        if {$disp > 1.0} {
            error "macro_score: injected placement for $tag is off by\
                ${disp}um; the injection did not land"
        }
        foreach s $EVAL_TAIL { ms_step $s }
        ms_leaf $tag [dict get $configs $tag STRATUM] $disp
    }]

    # The spine continues through its own default macro placement to
    # grt: the production reference this whole audit is anchored to.
    set ::ms_tail_s 0.0
    foreach s $MACRO_STEP { ms_step $s }
    ms_write_macros [file join $::ms_out spine.macros.json]
    foreach s $EVAL_TAIL { ms_step $s }
    ms_leaf spine spine 0.0
} else {
    error "macro_score: unknown MS_MODE '$::ms_mode'"
}

dict for {tag code} $statuses {
    if {$code != 0} {
        puts stderr "macro_score: member $tag failed with status $code;\
            its outputs are missing"
    }
}
puts "macro_score: walk complete"
exit 0
