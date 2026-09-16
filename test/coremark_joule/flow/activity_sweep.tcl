# Does OpenSTA's activity estimate change the answer?
#
# Counting annotated pins is necessary but not sufficient. What a reader
# needs is a *bound*: even if the estimator were wrong by any amount it
# could plausibly be wrong by, how much would the reported power move?
#
# OpenSTA supplies the lever. `set_power_activity -input` sets
# `input_activity_`, which is the density seeded into every levelization
# root that carries no annotation -- top-level input ports and tie-cell
# outputs. It is the *only* way a number OpenSTA invented enters the
# design; everything else is either annotated, propagated from these
# roots, or taken exactly from the SDC clock. Sweep it across its whole
# plausible range and the total power either moves or it does not.
#
# Use `-input`, never `-global`: `-global` short-circuits
# `Power::findActivity` and overrides *every* pin including the annotated
# ones, which would make the test pass by destroying what it measures.
#
# Two arms, because a null result is only evidence if the lever works:
#
#   vectorless  no SAIF. Power must move a lot -- this is the positive
#               control, and it is what calibrates the epsilon.
#   saif        the SAIF read. Power must not move.
#
# The sweep runs vectorless first because reading a SAIF cannot be undone
# within a session: `read_saif` populates the user activity map and there
# is no command that empties it.
#
# Required env:
#   STAGE_STEM     ORFS stage stem, e.g. 5_1_grt
#   SAIF_STIMULI   path to the .saif
#   SAIF_SCOPE     hierarchy in the SAIF matching the design root
#   SWEEP_POINTS   space-separated `arm|activity|path` triples. The
#                  caller spells out every output file, so a point and
#                  the file it lands in cannot drift apart.

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

log_cmd estimate_parasitics -global_routing

proc sweep_arm { arm points digits } {
    foreach point $points {
        lassign [split $point "|"] point_arm activity path
        if { $point_arm ne $arm } {
            continue
        }
        # -activity is in toggles per clock period: 0.0 is "an
        # unannotated root never toggles", 2.0 is "it toggles as often as
        # the clock". OpenSTA's own default is 0.1.
        set_power_activity -input -activity $activity
        # -digits, because the pass condition is "this number did not
        # move". report_power's default rounds to a handful of
        # significant figures, and at that resolution a flat arm is
        # indistinguishable from a small one -- the test would pass by
        # not being able to see.
        report_power -format json -digits $digits > $path
        puts "activity_sweep: $arm activity $activity -> [file tail $path]"
    }
}

set points $::env(SWEEP_POINTS)

# Enough figures that the difference the test looks for is resolvable.
set digits 10
if { [info exists ::env(POWER_DIGITS)] && $::env(POWER_DIGITS) ne "" } {
    set digits $::env(POWER_DIGITS)
}

sweep_arm "vectorless" $points $digits

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

sweep_arm "saif" $points $digits
