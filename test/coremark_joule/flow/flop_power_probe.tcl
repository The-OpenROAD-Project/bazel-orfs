# Why does a flop's internal power not scale with the clock period?
#
# §4.8's cross-check ran one synthesis netlist -- byte-identical across
# three packages -- at 1282, 2000 and 10000 ps. Combinational and macro
# power scaled with frequency to three digits, as the same toggles over a
# longer duration must; the Sequential group's internal power did not,
# so the flops' energy per cycle rose with the period. This probe asks
# OpenSTA to show its arithmetic for one flop: the per-pin internal
# power lines its power debug level prints (slew, duty, energy, density),
# so the term that moved is named rather than guessed.
#
# Required env: STAGE_STEM, SAIF_STIMULI, SAIF_SCOPE, OUT.

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc
read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

set out [open $::env(OUT) w]
set clk [lindex [all_clocks] 0]
puts $out "clock period [get_property $clk period]"

# One flop, the first of the library's DFFs in the netlist.
set flops [get_cells -hierarchical -filter "ref_name =~ DFF*"]
puts $out "flops [llength $flops]"
set inst [lindex $flops 0]
puts $out "instance [get_full_name $inst] ref [get_property $inst ref_name]"
close $out

# The per-pin internal-power arithmetic, appended to the same file via
# OpenSTA's report redirection so debug lines land beside the report.
sta::redirect_file_append_begin $::env(OUT)
sta::set_debug power 2
report_power -instances $inst -digits 6
sta::set_debug power 0
sta::redirect_file_end
