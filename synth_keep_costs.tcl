# Each module's own estimated gates, for keep_report.py: synth_keep.tcl's
# coarse synthesis and size model, with every module made a candidate.
# keep_hierarchy -min_cost 1 keeps each module it visits above one gate,
# so no module's size includes another's, and logs one line per module:
#   Keeping <module> (estimated size above threshold: <gates> > 1).
# Writes the log to KEEP_COSTS_OUT; synthesis never reads it.

source $::env(SCRIPTS_DIR)/synth_preamble.tcl
read_checkpoint $::env(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil

hierarchy -check -top $::env(DESIGN_NAME)
synth -run :fine

if { [info commands convert_liberty_areas] ne "" } {
  convert_liberty_areas
}
# A black box (a memory, a macro) counts as nothing: synthesis does not
# make its gates, and the report is about synthesis time.
setattr -mod -set gate_cost_equivalent 0 =A:blackbox
setattr -mod -unset keep_hierarchy =*
tee -q -o $::env(KEEP_COSTS_OUT) keep_hierarchy -min_cost 1
