# The minimum clock period, from register-to-register paths only.
#
# §3.8 of the study's paper argues the model: only reg2reg paths can
# fail timing closure, and everything touching a port is an optimisation
# target. This is that argument turned into a number.
#
# The overall WNS is not the right quantity here, and reporting it would
# understate every core in this study. It is the worst slack over *all*
# path groups, including in2reg, reg2out and in2out -- paths whose
# budgets are the 0.8/0.8/0.6 fractions the design's constraints.sdc
# chose, which stand in for a register outside every port. Those numbers
# are an assumption about how the CPU is connected to the world, and
# this study deliberately does not model that world: the core is
# attached to a clock-crossing bridge, a bus register or a GPIO pad, and
# which of those it is changes the budget without changing the design.
#
# So a frequency derived from the overall WNS would be limited by our
# own assumption rather than by the core. The reg2reg worst slack is the
# part that is a property of the design, and it is what `auto_period`
# (§5.7) will drive.
#
# The group is the platform's: $PLATFORM_DIR/constraints.sdc defines
# in2reg, reg2out, reg2reg and in2out with `group_path`, and this asks
# for reg2reg by name so the probe cannot drift from the file that
# constrains the design.
#
# Both are reported, because the difference between them is worth
# seeing: it is the size of the assumption.
#
# Required env:
#   STAGE_STEM   ORFS stage stem, e.g. 5_1_grt
#   OUT          output path

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

log_cmd estimate_parasitics -global_routing

# Two OpenSTA interfaces, two units, and they do not agree.
# sta::worst_slack_cmd returns seconds; `get_property <path> slack`
# returns the UI unit, which for asap7 is picoseconds. Scaling both
# gives a number 1e12 too large -- and on a design whose slack happens
# to be exactly zero, as VeeR's is, the mistake is invisible. It was
# caught by the three cores whose slack is not zero.
proc seconds_to_ps { value } {
    return [expr { $value * 1e12 }]
}

set clk [lindex [all_clocks] 0]
set period [get_property $clk period]

set overall 1.0e30
catch { set overall [sta::worst_slack_cmd "max"] }
if { abs($overall) > 1.0e20 } {
    set overall_ps "none"
} else {
    set overall_ps [seconds_to_ps $overall]
}

# Register to register, taken from the path group the platform SDC
# defines rather than re-derived here.
#
# $PLATFORM_DIR/constraints.sdc ends with four `group_path` commands --
# in2reg, reg2out, reg2reg, in2out -- so the partition this study
# reasons about is already the platform's own. Asking for the group by
# name means the probe cannot disagree with the file that constrains the
# design; writing `-from [all_registers] -to [all_registers]` here would
# be a second definition of the same thing, free to drift.
#
# The path count is reported too. A group that matches nothing and a
# group whose worst slack is zero both produce a zero, and they are very
# different facts.
# Several paths, not one. Asking for a single path and then reporting
# that one came back is not a check -- it only echoes the request. A
# slack of exactly 0.000000 is the suspicious case worth being able to
# distinguish, because repair_timing stops as soon as slack is
# non-negative and *could* legitimately land there, but landing on
# exactly zero to six decimals is a measure-zero event for a process
# that inserts discrete buffers.
#
# So: ask for a handful, report how many actually came back and what
# their slacks are. A run of distinct non-zero slacks says the group is
# real and the worst is real. A single zero, or a column of identical
# zeros, says something is clamping and the number should not be quoted.
set reg2reg_ps "none"
set reg2reg_worst_endpoint "none"
set paths [find_timing_paths -path_group reg2reg \
    -sort_by_slack -group_path_count 8]
set reg2reg_paths [llength $paths]
set reg2reg_slacks {}
foreach path $paths {
    lappend reg2reg_slacks [get_property $path slack]
}
if { $reg2reg_paths > 0 } {
    # Already in the UI unit; see seconds_to_ps above.
    set reg2reg_ps [lindex $reg2reg_slacks 0]
    catch {
        set reg2reg_worst_endpoint [get_full_name [get_property [lindex $paths 0] endpoint]]
    }
}

set fh [open $::env(OUT) w]
puts $fh "stage $::env(STAGE_STEM)"
puts $fh "clock [get_name $clk]"
puts $fh "period_ps $period"
puts $fh "wns_all_ps $overall_ps"
puts $fh "reg2reg_paths_returned $reg2reg_paths"
puts $fh "reg2reg_slacks_ps $reg2reg_slacks"
puts $fh "reg2reg_worst_endpoint $reg2reg_worst_endpoint"
puts $fh "wns_reg2reg_ps $reg2reg_ps"
if { $reg2reg_ps ne "none" } {
    puts $fh "achieved_period_ps [expr { $period - $reg2reg_ps }]"
    puts $fh "achieved_mhz [expr { 1.0e6 / ($period - $reg2reg_ps) }]"
}
close $fh
