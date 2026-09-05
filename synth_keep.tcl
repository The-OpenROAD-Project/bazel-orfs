# Coarse synthesis + keep_hierarchy decision.
# Produces 1_1_yosys_keep.rtlil listing modules to preserve.
# This is the first half of synth.tcl extracted so the keep list
# can be used to partition parallel synthesis jobs.

source $::env(SCRIPTS_DIR)/synth_preamble.tcl
read_checkpoint $::env(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil

hierarchy -check -top $::env(DESIGN_NAME)

if { [env_var_exists_and_non_empty SYNTH_KEEP_MODULES] } {
  set missing [list]
  foreach module $::env(SYNTH_KEEP_MODULES) {
    # rtlil::set_attr throws a clean Tcl error ("module not found") when the
    # module isn't in the elaborated design — caught silently here. Using
    # `select` instead would emit a "did not match any module" warning we
    # don't want on the happy path.
    if { [catch {rtlil::set_attr -mod $module keep_hierarchy 1}] } {
      lappend missing $module
    }
  }
  if { [llength $missing] > 0 } {
    error "SYNTH_KEEP_MODULES contains [llength $missing] module name(s) not present in the elaborated design (typos, post-refactor renames, or wrong-design list): [join $missing {, }]"
  }
}

# Coarse synthesis without flattening to get module sizes
synth -run :fine

# Which modules to keep as hierarchy boundaries. Mirrors ORFS's
# synth.tcl: SYNTH_MINIMUM_KEEP_SIZE is the threshold in estimated
# gates below which a module is flattened into its parent (asap7's
# platform default is 1000; riscv32i sets 10000, coralnpu 40000).
# e46fca0 dropped this on the theory that yosys's default keeps "all
# substantial modules"; it does not -- with no threshold keep_hierarchy
# marks every module, so riscv32i kept its 30-gate shifter (whose
# `input signed` ports OpenSTA then rejects) and coralnpu kept 131
# modules where ORFS keeps a handful. Diverging from ORFS here changes
# the netlist every hierarchical ORFS design gets under bazel.
#
# convert_liberty_areas is a proc from ORFS's synth_preamble.tcl that
# feeds liberty cell areas into the estimate; guarded so the block
# also runs where the preamble is not sourced (the unit tests drive
# these scripts on bare yosys), falling back to yosys's gate counts.
if { [env_var_exists_and_non_empty SYNTH_MINIMUM_KEEP_SIZE] } {
  set ungroup_threshold $::env(SYNTH_MINIMUM_KEEP_SIZE)
  puts "Keep modules above estimated size of $ungroup_threshold gate equivalents"
  if { [info commands convert_liberty_areas] ne "" } {
    convert_liberty_areas
  }
  keep_hierarchy -min_cost $ungroup_threshold
} else {
  keep_hierarchy
}

# Save RTLIL checkpoint after keep_hierarchy decisions.
# The kept module list (kept_modules.json) is extracted separately
# by rtlil_kept_modules.py for fast iteration.
write_rtlil $::env(RESULTS_DIR)/1_1_yosys_keep.rtlil
