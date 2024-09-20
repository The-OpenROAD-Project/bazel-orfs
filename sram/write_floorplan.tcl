source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

set f [file join $::env(WORK_HOME) "floorplan.def"]
write_def $f
