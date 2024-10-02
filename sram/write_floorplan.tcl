# Make a minimal floorplan.def that we can read in using
# FLOORPLAN_DEF
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.v 1_synth.sdc

set additional_args ""
append_env_var additional_args ADDITIONAL_SITES -additional_sites 1
initialize_floorplan -die_area $::env(DIE_AREA) \
                        -core_area $::env(CORE_AREA) \
                        -site $::env(PLACE_SITE) \
                        {*}$additional_args

set f [file join $::env(WORK_HOME) "floorplan.def"]
write_def $f
