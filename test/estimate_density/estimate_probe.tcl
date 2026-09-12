# PRE_GLOBAL_PLACE hook: ask gpl what density it thinks this design needs.
#
# OpenROAD #11395 adds `estimate_target_density`, which binary-searches the
# bins of a freshly initialized Nesterov state for the density that would
# produce a given overflow, without running global placement. This probe
# calls it at the only moment where the answer could be used -- immediately
# before ORFS runs global_placement -- and prints one machine-readable line
# per overflow target. harvest.py reads those lines out of
# 3_3_place_gp.log; nothing here writes a file, so the probe adds no
# declared output to the stage.
#
# Two things this probe deliberately does NOT do:
#
#   * It does not choose the density. The arm's density comes from ORFS's
#     own PLACE_DENSITY / PLACE_DENSITY_LB_ADDON, so a rung is a stock flow
#     run and the estimate is an observer of it, not a participant.
#   * It does not run on the unpatched binary. `estimate_target_density`
#     does not exist there, and the A/B arms that compare patched against
#     unpatched must run the same stage script either way, so the command's
#     absence is reported and skipped rather than raising.
#
# Caveat worth carrying into the report: this hook runs where ORFS puts it,
# which is before `remove_buffers` and `buffer_ports`. Global placement
# therefore sees a slightly different instance set than the estimate did.
# The uniform density is printed here and ORFS prints its own at
# global_placement time ("Placement density is ... lower bound ..."), so the
# size of that gap is measured rather than assumed.

proc estimate_density_json { pairs } {
    set parts {}
    foreach { key value } $pairs {
        if { [string is double -strict $value] } {
            lappend parts "\"$key\": $value"
        } else {
            lappend parts "\"$key\": \"$value\""
        }
    }
    return "{[join $parts {, }]}"
}

set probe_pad $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT)

# The same padding global_place.tcl passes to global_placement, so the
# estimate is asked about the placement the flow is about to attempt.
set probe_uniform [gpl::get_global_placement_uniform_density \
    -pad_left $probe_pad -pad_right $probe_pad]

set probe_have_cmd [expr { [info commands estimate_target_density] ne "" }]

puts "ESTDENSITY_JSON [estimate_density_json [list \
    kind context \
    design $::env(DESIGN_NAME) \
    uniform_density $probe_uniform \
    pad $probe_pad \
    place_density [env_var_or_empty PLACE_DENSITY] \
    place_density_lb_addon [env_var_or_empty PLACE_DENSITY_LB_ADDON] \
    command_available [expr { $probe_have_cmd ? 1 : 0 }]]]"

if { !$probe_have_cmd } {
    puts "ESTDENSITY_JSON [estimate_density_json [list \
        kind skipped \
        reason {estimate_target_density not in this binary}]]"
    return
}

# Three overflow targets: 0.1 is what global_placement defaults to and
# therefore the one the table compares against; 0.05 and 0.2 say how the
# estimate responds to the knob at all, which a single point cannot.
set probe_drive [expr { [env_var_exists_and_non_empty ESTIMATE_DRIVES_DENSITY] \
    && $::env(ESTIMATE_DRIVES_DENSITY) }]

foreach probe_overflow { 0.05 0.1 0.2 } {
    set probe_start [clock milliseconds]
    set probe_density [estimate_target_density \
        -overflow $probe_overflow \
        -pad_left $probe_pad \
        -pad_right $probe_pad]
    set probe_elapsed [expr { ([clock milliseconds] - $probe_start) / 1000.0 }]
    puts "ESTDENSITY_JSON [estimate_density_json [list \
        kind estimate \
        overflow $probe_overflow \
        estimated_density $probe_density \
        uniform_density $probe_uniform \
        elapsed_s $probe_elapsed]]"

    # The arm that uses the feature as a user would: hand global
    # placement the density the command just asked for, at the overflow
    # global placement is about to aim for. PLACE_DENSITY_LB_ADDON is
    # cleared because `place_density_with_lb_addon` prefers it whenever
    # it is set, and would otherwise quietly ignore what we put in
    # PLACE_DENSITY.
    if { $probe_drive && $probe_overflow == 0.1 } {
        set ::env(PLACE_DENSITY_LB_ADDON) ""
        set ::env(PLACE_DENSITY) $probe_density
        puts "ESTDENSITY_JSON [estimate_density_json [list \
            kind drive \
            overflow $probe_overflow \
            driven_density $probe_density]]"
    }
}
