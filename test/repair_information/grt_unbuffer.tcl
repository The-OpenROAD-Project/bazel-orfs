# Rip out the early repair's buffers before global route.
#
# PRE_GLOBAL_ROUTE_TCL, so this runs on the CTS output before
# global_route.tcl routes anything and before the global-route repair
# runs. The hypothesis: the CTS-stage repair spends 30.3 um2 of logic
# area for a period change that does not resolve, so removing its work
# and letting the well-informed repair start from a clean netlist should
# recover the area without costing the period.
#
# Wholesale, deliberately. The companion arm (grt_unbuffer_seq.tcl) lets
# the resizer choose which buffers to remove; this one removes every
# signal buffer it is allowed to, so the two together answer whether
# selection matters or only removal does.
#
# Three exclusions, each of which would otherwise break the run rather
# than bias it:
#
#   * clock nets. After CTS the clock tree *is* buffers, and removing
#     them removes the clock. dbNet's signal type is the flow's own
#     classification, so this uses that rather than a name pattern.
#   * dont-touch instances. The resizer records them for a reason and
#     remove_buffers would either refuse or silently undo a constraint.
#   * anything that is not a buffer. Read from the liberty rather than
#     from a name prefix: asap7's buffers are BUFx*, but a name test
#     that happens to work on one platform is a name test that fails
#     silently on the next.

set ub_block [ord::get_db_block]

# Buffer masters, from the liberty's own classification.
set ub_buffer_masters [dict create]
foreach ub_lib_cell [get_lib_cells *] {
    if { [catch { get_property $ub_lib_cell is_buffer } ub_is] } {
        continue
    }
    if { $ub_is } {
        dict set ub_buffer_masters [get_name $ub_lib_cell] 1
    }
}

if { [dict size $ub_buffer_masters] == 0 } {
    error "no liberty cell reports is_buffer: the classification this\
 relies on is not available, and removing by name pattern instead would\
 be a different experiment"
}

set ub_victims {}
set ub_skipped_clock 0
set ub_skipped_dont_touch 0

foreach ub_inst [$ub_block getInsts] {
    set ub_master_name [[$ub_inst getMaster] getName]
    if { ![dict exists $ub_buffer_masters $ub_master_name] } {
        continue
    }
    if { [$ub_inst isDoNotTouch] } {
        incr ub_skipped_dont_touch
        continue
    }
    # Any terminal on a clock net makes this part of the clock network.
    set ub_is_clock 0
    foreach ub_iterm [$ub_inst getITerms] {
        set ub_net [$ub_iterm getNet]
        if { $ub_net ne "NULL" && [$ub_net getSigType] eq "CLOCK" } {
            set ub_is_clock 1
            break
        }
    }
    if { $ub_is_clock } {
        incr ub_skipped_clock
        continue
    }
    lappend ub_victims [$ub_inst getName]
}

puts "GRT_UNBUFFER candidates=[llength $ub_victims]\
 skipped_clock=$ub_skipped_clock skipped_dont_touch=$ub_skipped_dont_touch"

if { [llength $ub_victims] > 0 } {
    # get_cells on the collected names rather than on a wildcard: the
    # names are what the exclusions above were decided on, and a second
    # selection here could quietly disagree with the first.
    log_cmd remove_buffers [get_cells $ub_victims]
    puts "GRT_UNBUFFER removed=[llength $ub_victims]"
} else {
    puts "GRT_UNBUFFER removed=0 -- nothing to remove, which is itself a result"
}

# Placement is left with holes where the buffers were. The flow's own
# grt stage runs detailed_placement after its repair, so legalisation is
# not this hook's job -- but the holes are real and the arm's placement
# is therefore not the baseline's, which is a stated confound rather
# than a controlled one.
