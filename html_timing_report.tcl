source $::env(SCRIPTS_DIR)/open.tcl
web_save_report -setup_paths 1000 -hold_paths 1000 [file join $::env(WORK_HOME) $::env(OUTPUT)]
