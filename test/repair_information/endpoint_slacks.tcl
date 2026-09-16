# One instrument's opinion of every endpoint in the design.
#
# The study's question is whether `repair_timing` helps because of its
# policy or because of its information, and "information" here means one
# specific thing: which endpoints a given parasitics model says are
# critical, and in what order. A repair that is handed the same ranking
# makes the same decisions no matter how good the underlying numbers
# are, so the ranking -- not the magnitude -- is what has to move before
# any of this can matter.
#
# So this probe reports a per-endpoint worst slack under exactly one
# instrument, named by RI_PARASITICS:
#
#   placement       estimate_parasitics -placement   (FLUTE Steiner x
#                   the single layer-averaged RC set_wire_rc installed)
#   global_routing  a global route, then
#                   estimate_parasitics -global_routing
#   spef            the extracted parasitics of a routed design
#
# Endpoints, not paths, because the endpoint set is the one thing that
# survives the flow: repair inserts buffers and CTS builds a tree, so the
# instances and nets differ between two stages of the same design, but a
# register's data pin is still the same pin at 3_place and at 6_final.
# That is what makes a rank comparison between stages meaningful at all.
#
# RI_GRT_ARGS carries the global_route arguments verbatim for the
# global_routing mode, which is what makes the trial-route cost/accuracy
# ladder a list of strings in a BUILD file rather than a script per rung.

# RESULTS_DIR belongs to the package declaring this run, not to the one
# that built the src, so stage the src's artifacts in before load.tcl
# looks for them.
source $::env(STAGE_SRC_TCL)

source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $stage_src_staged]
set stage_stem [file rootname $odb_tail]
set sdc_tail $stage_stem.sdc
load_design $odb_tail $sdc_tail

set mode $::env(RI_PARASITICS)
set arm [expr { [info exists ::env(RI_ARM)] ? $::env(RI_ARM) : $mode }]

# Elapsed seconds around the expensive step. `clock` lives in clock.tcl
# and is auto-loaded from TCL_LIBRARY, which a hermetic runfiles tree does
# not always ship -- util.tcl's log_cmd guards for exactly this -- so a
# missing `clock` costs the timing column, not the run.
set has_clock [expr { [info commands clock] ne "" }]
proc now { } {
    if { [info commands clock] eq "" } {
        return 0
    }
    return [expr { [clock milliseconds] / 1000.0 }]
}

# The clock treatment is a property of the stage, not a choice this probe
# gets to make: before CTS there is no tree to propagate, after it there
# is, and ORFS's own scripts propagate from global route on. Recorded in
# the output either way, because an ideal-clock reading and a propagated
# one are not comparable and a reader must be able to see which is which.
set propagated 0
if { [llength [get_clocks]] > 0 && ![catch { sta::clocks_propagated }] } {
    set propagated [sta::clocks_propagated]
}

set grt_seconds 0
set pin_access_seconds 0
set guides 0

if { $mode eq "placement" } {
    set t0 [now]
    log_cmd estimate_parasitics -placement
    set grt_seconds [expr { [now] - $t0 }]
} elseif { $mode eq "global_routing" } {
    set grt_args [expr { [info exists ::env(RI_GRT_ARGS)] ? $::env(RI_GRT_ARGS) : "" }]

    # The clock has to be propagated for a post-CTS stage to report the
    # timing the flow would see; before CTS there is nothing to
    # propagate and asking for it is a no-op on an ideal clock.
    set_propagated_clock [all_clocks]

    # ORFS runs pin_access before global_route, so a trial route that
    # skipped it would not be the same operation the flow performs. It is
    # timed separately rather than folded into the route: the cost
    # question this ladder answers is "what would a repair hook have to
    # pay", and if pin access dominates, a cheaper congestion setting
    # buys nothing and the ladder has to say so.
    if { ![info exists ::env(RI_PIN_ACCESS)] || $::env(RI_PIN_ACCESS) ne "0" } {
        set t0 [now]
        log_cmd pin_access
        set pin_access_seconds [expr { [now] - $t0 }]
    }

    set t0 [now]
    log_cmd global_route {*}$grt_args
    set grt_seconds [expr { [now] - $t0 }]

    # grt::have_routes is the gate estimate_parasitics itself uses, and
    # it returns false for a congested route unless -allow_congestion
    # was passed. Checking it here turns "EST-5: Run global_route
    # before estimating parasitics" -- which reads as though the route
    # never happened -- into a statement about the arm's own arguments.
    if { ![grt::have_routes] } {
        error "global_route produced no usable routes for arm $arm.\
 A trial route with overflow remaining needs -allow_congestion, or\
 grt::have_routes rejects it and the parasitics cannot be estimated.\
 Arguments were: $grt_args"
    }
    log_cmd estimate_parasitics -global_routing
} elseif { $mode eq "spef" } {
    set spef [file join $::env(RESULTS_DIR) $stage_stem.spef]
    if { ![file exists $spef] } {
        error "RI_PARASITICS=spef needs $stage_stem.spef beside the ODB;\
 only the final stage has one"
    }
    set_propagated_clock [all_clocks]
    set t0 [now]
    log_cmd read_spef $spef
    set grt_seconds [expr { [now] - $t0 }]
} else {
    error "RI_PARASITICS must be placement, global_routing or spef, not $mode"
}

# Guide count, for the global_routing arms: a trial route that skipped
# large-fanout nets or bailed early still produces a well-formed slack
# for every endpoint, so the only way to see that it routed less of the
# design is to count what carries guides.
set block [ord::get_db_block]
foreach net [$block getNets] {
    if { [llength [$net getGuides]] > 0 } {
        incr guides
    }
}

# One worst path per endpoint. -endpoint_path_count 1 with
# -unique_paths_to_endpoint is what makes the result a function of the
# endpoint rather than of how many paths happen to reach it, and the
# group count is set far above the endpoint count so the search is not
# the thing that truncates the list.
#
# `-to [all_registers]` rather than `-path_group reg2reg`: the reg2reg
# group is created by the *platform* constraints.sdc, which a stage's
# written-out SDC does not carry, so asking for it here gets
# "STA-0527 unknown path group" and a silent fall back to every path in
# the design -- a well-formed ranking of a different question. Selecting
# the endpoints directly says what is meant and needs nothing but the
# design.
#
# It is a slightly wider set than reg2reg: an endpoint's worst path may
# start at an input port rather than at a register. That is the right
# set for this study -- repair works on endpoints whatever feeds them --
# but it means the WNS here is not necessarily ORFS's reg2reg WNS, and
# the selection is recorded in the output so the two are never confused.
set endpoints [all_registers]
if { [llength $endpoints] == 0 } {
    error "no registers at $stage_stem: nothing to rank"
}
set paths [find_timing_paths -to $endpoints -sort_by_slack \
    -group_path_count 1000000 -endpoint_path_count 1 \
    -unique_paths_to_endpoint]

if { [llength $paths] == 0 } {
    error "no timing paths to a register at $stage_stem: nothing to rank"
}

set clock_period [get_property [lindex [get_clocks] 0] period]
set wns [get_property [lindex $paths 0] slack]

set rows {}
foreach path $paths {
    set ep [get_full_name [get_property $path endpoint]]
    set slack [get_property $path slack]
    lappend rows [format {{"endpoint": "%s", "slack": %.6g}} $ep $slack]
}

puts [format "RI_ENDPOINTS arm=%s stage=%s mode=%s endpoints=%d guides=%d\
 wns=%.6g min_period=%.6g seconds=%.2f pin_access=%.2f" \
    $arm $stage_stem $mode [llength $rows] $guides $wns \
    [expr { $clock_period - $wns }] $grt_seconds $pin_access_seconds]

set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"arm\": \"$arm\","
puts $fp "  \"stage\": \"$stage_stem\","
puts $fp "  \"parasitics\": \"$mode\","
puts $fp "  \"path_selection\": \"-to \[all_registers\]\","
puts $fp "  \"grt_args\": \"[expr { [info exists ::env(RI_GRT_ARGS)] ? $::env(RI_GRT_ARGS) : {} }]\","
puts $fp "  \"propagated_clock\": [expr { $propagated ? "true" : "false" }],"
puts $fp "  \"clock_period\": $clock_period,"
puts $fp "  \"wns\": $wns,"
puts $fp "  \"min_period\": [expr { $clock_period - $wns }],"
puts $fp "  \"seconds\": [format %.3f $grt_seconds],"
puts $fp "  \"pin_access_seconds\": [format %.3f $pin_access_seconds],"
puts $fp "  \"nets_with_guides\": $guides,"
puts $fp "  \"endpoints\": \["
puts $fp "    [join $rows ",\n    "]"
puts $fp "  \]"
puts $fp "}"
close $fp
exit 0
