source $::env(SCRIPTS_DIR)/floorplan.tcl

set f [file join $::env(WORK_HOME) "floorplan.def"]
write_def $f
