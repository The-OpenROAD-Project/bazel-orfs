# One rung of the min-period ladder: what `clk_period - WNS` reads as at
# one stage, and which parasitics the flow used to get there.
#
# The measurement is deliberately NOT built out of load.tcl's
# load_design. What a stage's timing says depends entirely on the
# parasitics and clock treatment ORFS picks for that stage -- floorplan
# gets set_wire_rc and no estimate at all, place and cts get
# `estimate_parasitics -placement`, grt gets `-global_routing`, final
# reads the SPEF -- and open.tcl's read_timing is the only place that
# choice is written down. Reimplementing it is how a ladder ends up
# comparing a stage against itself under different rules and calling the
# difference a stage effect.
#
# So: source ORFS's open.tcl with GUI_TIMING off (it then only reads the
# ODB and defines read_timing), then call read_timing. The rung reports
# the design_stage open.tcl derived and the parasitics branch that
# implies, so a reader can see the instrument changed between rungs
# rather than having to trust that it did not.

# Staging, and the name of this rung. Both come from the shared probe
# preamble: RESULTS_DIR belongs to the declaring package, so a src built
# elsewhere has to be copied in before load.tcl or open.tcl can find it.
source $::env(STAGE_SRC_TCL)
set odb $stage_src_staged
# The rung's name comes from the ODB it measured, not from a variable the
# caller sets: a label and a file that can disagree eventually do.
set ladder_stage [file rootname [file tail $odb]]

# GUI_TIMING=1 is what makes open.tcl read the design *and* its timing:
# read_liberty first, then read_timing. Sourcing it with GUI_TIMING=0 and
# calling read_timing by hand looks equivalent and is not -- liberty is
# never read, so STA has no command units and the first timing query
# fails with ORD-0013. Units are exactly the thing worth not
# hand-rolling here: a period read in STA-internal seconds against a
# slack in user units would produce a plausible min_period that is wrong
# by a factor of a thousand.
#
# The gui:: calls open.tcl makes under this flag are guarded by
# [gui::enabled], which is false in batch.
set ::env(GUI_TIMING) 1
set ::env(ODB_FILE) $odb
source $::env(SCRIPTS_DIR)/open.tcl

# Which instrument read_timing chose. Taken from util.tcl's own
# find_sdc_file rather than re-derived from the file name.
set stage_info [find_sdc_file $odb]
set design_stage [lindex $stage_info 0]

if { $design_stage >= 6 && [file exists $::env(RESULTS_DIR)/6_final.spef] } {
    set parasitics "spef"
} elseif { $design_stage >= 5 } {
    set parasitics [expr { [grt::have_routes] ? "global_routing" : "none" }]
} elseif { $design_stage >= 3 } {
    set parasitics "placement"
} else {
    set parasitics "set_wire_rc"
}
set propagated [expr { $design_stage >= 4 ? 1 : 0 }]

# The one copy of the sampling logic, shared with the estimation ladder:
# a study comparing spreads across ensembles is only as good as the
# identity of its measurement.
source $::env(EXTRACT_LIB_TCL)
set sample [extract_sample_paths]

set clock_period [dict get $sample clock_period]
set wns [dict get $sample wns]

# Read the constraint back and assert it. A clock period that silently
# failed to apply is the worst kind of failure here: every rung would
# still report a well-formed min_period, the ladder would still have a
# shape, and the numbers would be answers to a question nobody asked.
# Tolerance is loose because the comparison is between the requested
# period in picoseconds and STA's own units, not between two floats.
if { [info exists ::env(WIREBOUND_CLK_PERIOD_PS)]
     && $::env(WIREBOUND_CLK_PERIOD_PS) ne "" } {
    set requested $::env(WIREBOUND_CLK_PERIOD_PS)
    if { abs($clock_period - $requested) > 0.01 * $requested } {
        error "clock period did not take: asked for $requested\
 ([sta::unit_scale_abbreviation time][sta::unit_suffix time]),\
 STA reports $clock_period"
    }
}

# And assert there is something to repair. A design that closes reports a
# clean zero delta for every repair knob the study sweeps, which looks
# exactly like a knob that does nothing.
if { $wns >= 0 } {
    puts "LADDER_WARNING stage=$ladder_stage closes with WNS $wns:\
 repair-knob arms measured on this rung cannot distinguish a knob that\
 does nothing from a design with nothing to do"
}
# The metric the whole study is about. Same identity check_pareto.py
# uses for its period axis: clock - WNS, never WNS on its own.
set min_period [expr { $clock_period - $wns }]

puts "LADDER stage=$ladder_stage design_stage=$design_stage\
 parasitics=$parasitics propagated=$propagated\
 clock_period=$clock_period wns=$wns min_period=$min_period"

set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"stage\": \"$ladder_stage\","
puts $fp "  \"design_stage\": $design_stage,"
puts $fp "  \"parasitics\": \"$parasitics\","
puts $fp "  \"propagated_clock\": $propagated,"
puts $fp "  \"time_unit\": \"[sta::unit_scale_abbreviation time][sta::unit_suffix time]\","
puts $fp "  \"clock_period\": $clock_period,"
puts $fp "  \"wns\": $wns,"
puts $fp "  \"min_period\": $min_period"
puts $fp "}"
close $fp
exit 0
