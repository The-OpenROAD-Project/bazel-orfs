# Coarse synthesis + keep_hierarchy decision.
# Produces 1_1_yosys_keep.rtlil listing modules to preserve.
# This is the first half of synth.tcl extracted so the keep list
# can be used to partition parallel synthesis jobs.

source $::env(SCRIPTS_DIR)/synth_preamble.tcl
read_checkpoint $::env(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil

hierarchy -check -top $::env(DESIGN_NAME)

if { [env_var_exists_and_non_empty SYNTH_KEEP_MODULES] } {
  foreach module $::env(SYNTH_KEEP_MODULES) {
    select -module $module
    setattr -mod -set keep_hierarchy 1
    select -clear
  }
}

# Coarse synthesis without flattening to get module sizes
synth -run :fine

if { [env_var_exists_and_non_empty SYNTH_MINIMUM_KEEP_SIZE] } {
  set ungroup_threshold $::env(SYNTH_MINIMUM_KEEP_SIZE)
  puts "Keep modules above estimated size of $ungroup_threshold gate equivalents"
  convert_liberty_areas
  keep_hierarchy -min_cost $ungroup_threshold
} else {
  keep_hierarchy
}

# Save RTLIL checkpoint after keep_hierarchy decisions.
# The kept module list (kept_modules.json) is extracted separately
# by rtlil_kept_modules.py for fast iteration.
write_rtlil $::env(RESULTS_DIR)/1_1_yosys_keep.rtlil
