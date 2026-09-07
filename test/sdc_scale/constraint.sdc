# The shape of a real large asap7 design's constraints: a handful of
# human-written lines that hand everything to the platform's
# constraints.sdc.  That file constrains [all_inputs] -> [all_registers]
# and [all_registers] -> [all_outputs] with three set_max_delay and four
# group_path commands.  write_sdc expands each of those seven into an
# explicit list of every register clock pin in the design, which is why
# the generated 1_synth.sdc -- and every read_sdc of it -- scales with the
# register count.
set clk_name clock
set clk_port_name clock
set clk_period 1000

# Ignore the synchronous reset.
if { [llength [get_ports -quiet reset]] == 1 } {
  set_false_path -from [get_ports reset]
}

set in2reg_max 900
set reg2out_max 900
set in2out_max 900

if { [llength [all_registers]] > 0 } {
  source $env(PLATFORM_DIR)/constraints.sdc
}
