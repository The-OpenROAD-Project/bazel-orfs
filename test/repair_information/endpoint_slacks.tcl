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

    # Contention, as a knob.
    #
    # The routing window and the per-layer derate are not session state:
    # ORFS installs them once at floorplan by sourcing FASTROUTE_TCL, and
    # they persist in the ODB's tech (dbTechLayer::setLayerAdjustment,
    # dbBlock::setMinRoutingLayer), which is why global_route.tcl never
    # re-sources it and why a probe that does nothing here still routes
    # under the flow's real supply.
    #
    # Which also makes them settable here, on the same CTS ODB, with no
    # new flow run. That is the study's contention axis: placement prices
    # every net from one layer-averaged RC constant, so the two
    # instruments can only disagree when routing is pushed onto layers
    # whose real RC is not that constant. Scarcer supply (a bigger
    # derate) pushes nets up the stack; a lower ceiling pushes them down.
    # Either way the question is the same -- how far from the constant
    # does the mix have to get before the period moves.
    if { [info exists ::env(RI_MAX_ROUTING_LAYER)]
         && $::env(RI_MAX_ROUTING_LAYER) ne "" } {
        set ri_min [expr { [info exists ::env(MIN_ROUTING_LAYER)]
                           ? $::env(MIN_ROUTING_LAYER) : "M2" }]
        log_cmd set_routing_layers \
            -signal $ri_min-$::env(RI_MAX_ROUTING_LAYER)
    }
    if { [info exists ::env(RI_LAYER_ADJUSTMENT)]
         && $::env(RI_LAYER_ADJUSTMENT) ne "" } {
        set ri_min [expr { [info exists ::env(MIN_ROUTING_LAYER)]
                           ? $::env(MIN_ROUTING_LAYER) : "M2" }]
        set ri_max [expr { [info exists ::env(RI_MAX_ROUTING_LAYER)]
                           && $::env(RI_MAX_ROUTING_LAYER) ne ""
                           ? $::env(RI_MAX_ROUTING_LAYER)
                           : $::env(MAX_ROUTING_LAYER) }]
        log_cmd set_global_routing_layer_adjustment \
            $ri_min-$ri_max $::env(RI_LAYER_ADJUSTMENT)
    }

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
#
# The per-layer split is the mechanism, not a decoration. `estimate_parasitics
# -placement` prices every net from the single resistance and capacitance
# `set_wire_rc` installed -- on asap7 an absolute constant corresponding
# to a lower-middle layer -- so placement and global route can only
# disagree to the extent that routing actually lands on layers whose RC
# is not that constant. If demand never reaches the top of the stack, the
# constant is not wrong about anything and there is nothing for a better
# instrument to correct. That has to be read off the guides rather than
# assumed from the layer window, which only says where routing was
# *permitted* to go.
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
array set guide_len {}
foreach net [$block getNets] {
    set net_guides [$net getGuides]
    if { [llength $net_guides] > 0 } {
        incr guides
    }
    foreach guide $net_guides {
        set lname [[$guide getLayer] getName]
        if { ![info exists guide_len($lname)] } {
            set guide_len($lname) 0.0
        }
        set box [$guide getBox]
        set w [expr { ([$box xMax] - [$box xMin]) * 1.0 / $dbu }]
        set h [expr { ([$box yMax] - [$box yMin]) * 1.0 / $dbu }]
        # A guide's corridor runs along its longer side.
        set guide_len($lname) \
            [expr { $guide_len($lname) + ($w > $h ? $w : $h) }]
    }
}

# Demand is only half of "is this layer busy". Track supply is the core
# extent across the layer's routing direction divided by its pitch, times
# the extent along it -- microns of corridor, the same unit as demand, so
# the ratio is dimensionless. asap7's upper layers are coarse (M8/M9
# pitch 0.08um against M2's 0.045um), so they hold far fewer tracks and a
# small share of total demand can still be most of what they can carry.
#
# Reported for every routing layer in the tech, not only those carrying
# guides: a layer with zero demand is a measurement, and dropping the row
# would make an unused layer indistinguishable from a missing one.
set core [$block getCoreArea]
set core_w [expr { ([$core xMax] - [$core xMin]) * 1.0 / $dbu }]
set core_h [expr { ([$core yMax] - [$core yMin]) * 1.0 / $dbu }]

set tech [[ord::get_db] getTech]
set layer_rows {}
foreach layer [$tech getLayers] {
    if { [$layer getRoutingLevel] == 0 } {
        continue
    }
    set lname [$layer getName]
    set pitch [expr { [$layer getPitch] * 1.0 / $dbu }]
    set dir [$layer getDirection]
    set demand [expr { [info exists guide_len($lname)] ? $guide_len($lname) : 0.0 }]
    if { $pitch > 0 } {
        set supply [expr { $dir eq "HORIZONTAL"
                           ? ($core_h / $pitch) * $core_w
                           : ($core_w / $pitch) * $core_h }]
    } else {
        set supply 0.0
    }
    lappend layer_rows [format \
        {{"layer": "%s", "level": %d, "direction": "%s", "pitch_um": %g, "demand_um": %.3f, "supply_um": %.3f}} \
        $lname [$layer getRoutingLevel] $dir $pitch $demand $supply]
}

# One worst path per endpoint. -endpoint_path_count 1 with
# -unique_paths_to_endpoint is what makes the result a function of the
# endpoint rather than of how many paths happen to reach it, and the
# group count is set far above the endpoint count so the search is not
# the thing that truncates the list.
#
# Register to register, and nothing else.
#
# Two ways to get this wrong, and this probe has been through both.
#
# `-path_group reg2reg` is what the flow's own reports use, but the
# group is created by the *platform* constraints.sdc and a stage's
# written-out SDC does not carry the group_path commands. Asking for it
# here gets "STA-0527 unknown path group" and then silently ranks every
# path in the design -- a well-formed answer to a different question.
#
# `-to [all_registers]` fixes that and introduces a subtler version of
# the same error. asap7's constraints.sdc deliberately uses no
# set_input_delay/set_output_delay: io-to-reg, reg-to-io and io-to-io
# are constrained with `set_max_delay -ignore_clock_latency` (80 ps by
# default) as *optimization targets*, and the clock period is reserved
# for register-to-register paths, which that file calls "the only thing
# that can fail timing closure". So `-to [all_registers]` admits in2reg
# paths whose slack is measured against an 80 ps budget with clock
# latency ignored -- not against the clock at all. `clk_period - WNS`
# built on one of those is not a period, and mixing them with reg2reg
# paths compares two different clock treatments.
#
# `-from [all_registers] -to [all_registers]` is the set the study
# means, and it needs nothing but the design.
set registers [all_registers]
if { [llength $registers] == 0 } {
    error "no registers at $stage_stem: nothing to rank"
}
set paths [find_timing_paths -from $registers -to $registers -sort_by_slack \
    -group_path_count 1000000 -endpoint_path_count 1 \
    -unique_paths_to_endpoint]

if { [llength $paths] == 0 } {
    error "no register-to-register paths at $stage_stem: nothing to rank"
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
puts $fp "  \"path_selection\": \"-from \[all_registers\] -to \[all_registers\]\","
puts $fp "  \"grt_args\": \"[expr { [info exists ::env(RI_GRT_ARGS)] ? $::env(RI_GRT_ARGS) : {} }]\","
puts $fp "  \"propagated_clock\": [expr { $propagated ? "true" : "false" }],"
puts $fp "  \"clock_period\": $clock_period,"
puts $fp "  \"wns\": $wns,"
puts $fp "  \"min_period\": [expr { $clock_period - $wns }],"
puts $fp "  \"seconds\": [format %.3f $grt_seconds],"
puts $fp "  \"pin_access_seconds\": [format %.3f $pin_access_seconds],"
puts $fp "  \"nets_with_guides\": $guides,"
puts $fp "  \"max_routing_layer\": \"[expr { [info exists ::env(RI_MAX_ROUTING_LAYER)] && $::env(RI_MAX_ROUTING_LAYER) ne {} ? $::env(RI_MAX_ROUTING_LAYER) : $::env(MAX_ROUTING_LAYER) }]\","
puts $fp "  \"layer_adjustment\": \"[expr { [info exists ::env(RI_LAYER_ADJUSTMENT)] && $::env(RI_LAYER_ADJUSTMENT) ne {} ? $::env(RI_LAYER_ADJUSTMENT) : $::env(ROUTING_LAYER_ADJUSTMENT) }]\","
puts $fp "  \"layers\": \[[join $layer_rows ", "]\],"
puts $fp "  \"endpoints\": \["
puts $fp "    [join $rows ",\n    "]"
puts $fp "  \]"
puts $fp "}"
close $fp
exit 0
