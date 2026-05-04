source $::env(SCRIPTS_DIR)/load.tcl

# Slack-margin heuristic: emits SETUP_SLACK_MARGIN + HOLD_SLACK_MARGIN
# from the previous stage's worst slack, plus a Δ safety budget so the
# next stage's repair_timing has a defined target instead of "fix to ≥ 0".
#
# One TCL handles every stage of the chain (synth→floorplan, place→cts,
# cts→grt, ...). Each invocation (via orfs_arguments) runs in the
# previous stage's RESULTS_DIR, so the canonical ODB is just the latest
# file present. Search from late to early — whichever exists wins. The
# script is identical regardless of which downstream stage will consume
# the JSON; the destination is only encoded in the orfs_arguments
# target name.

set candidates {
    {4_cts.odb       4_cts.sdc}
    {3_place.odb     3_place.sdc}
    {2_floorplan.odb 2_floorplan.sdc}
    {1_synth.odb     1_synth.sdc}
}
foreach pair $candidates {
    set odb_file [lindex $pair 0]
    set sdc_file [lindex $pair 1]
    if { [file exists $::env(RESULTS_DIR)/$odb_file] } {
        load_design $odb_file $sdc_file
        break
    }
}

# Worst slacks in the user's current time unit (round-trip safe with
# repair_timing's -setup_margin / -hold_margin via sta::time_ui_sta).
set setup_wns [sta::time_sta_ui [sta::worst_slack_cmd "max"]]
set hold_whs  [sta::time_sta_ui [sta::worst_slack_cmd "min"]]

# Sentinel handling: OpenSTA returns ~1e30 when no path exists (e.g. an
# unconstrained pre-CTS design has no real hold path). Fall back to
# generous defaults that trigger no useful repair work.
proc finite_or_default { v default } {
    if { ![string is double -strict $v] || abs($v) > 1.0e20 } {
        return $default
    }
    return $v
}
set setup_wns [finite_or_default $setup_wns -12000]
set hold_whs  [finite_or_default $hold_whs  -1000]

# Margin formula: min(slack, 0) - Δ.
#
# Two cases:
# - Pre-stage slack ≤ 0 (real violation): margin = slack - Δ. repair_timing
#   sees current state already meets margin (slack ≥ slack - Δ), no work.
# - Pre-stage slack > 0 (no current violation, e.g. synth often has positive
#   WHS): margin = 0 - Δ = -Δ. Acts as a generous floor that lets the next
#   stage absorb real violations emerging from layout (e.g. CTS adding
#   hold violations from real clock latency) without triggering futile
#   repair.
#
# Δ is the "safety margin" — how much degradation we allow from pre-stage
# state. Δ=0 is a trap: if the previous stage had positive slack but the
# next stage introduces violations, margin = 0 means "fix to ≥ 0," the
# futile-tight regime which has been observed to cause hundreds of repair
# passes and eventual ODB-1200 crashes. Δ=1000 ps is data-validated:
# end-to-end runs have landed hold repair within a fraction of a ps of
# the -1000 margin, indicating Δ was tight enough to be useful but loose
# enough to converge.

proc clamp_at_zero { v } { return [expr {$v < 0 ? $v : 0}] }
set setup_wns [clamp_at_zero $setup_wns]
set hold_whs  [clamp_at_zero $hold_whs]

proc env_or_default { name default } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

set DELTA_SETUP [env_or_default DELTA_SETUP_PS 1000]
set DELTA_HOLD  [env_or_default DELTA_HOLD_PS  1000]

set setup_margin [expr {$setup_wns - $DELTA_SETUP}]
set hold_margin  [expr {$hold_whs  - $DELTA_HOLD}]

puts "compute_slack_margin: previous-stage WNS=$setup_wns, WHS=$hold_whs (user time units, clamped at zero)"
puts "compute_slack_margin: SETUP_SLACK_MARGIN=$setup_margin, HOLD_SLACK_MARGIN=$hold_margin (ΔSETUP=$DELTA_SETUP ps, ΔHOLD=$DELTA_HOLD ps)"

set f [open $::env(OUTPUT) w]
puts $f "{\"SETUP_SLACK_MARGIN\": \"$setup_margin\", \"HOLD_SLACK_MARGIN\": \"$hold_margin\"}"
close $f
