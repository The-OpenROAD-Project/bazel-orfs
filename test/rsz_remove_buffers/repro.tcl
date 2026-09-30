# remove_buffers, then repair_design -pre_placement, on a synthesis ODB:
# the sequence that stopped OpenROAD on XiangShan's Frontend
# (ideas/xiangshan-frontend-synth.md). OUTPUT names a file written only
# when both return.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb 1_synth.sdc
set before [llength [[ord::get_db_block] getInsts]]
remove_buffers
repair_design -pre_placement
set f [open $::env(OUTPUT) w]
puts $f "completed: $before instances before, [llength [[ord::get_db_block] getInsts]] after"
close $f
