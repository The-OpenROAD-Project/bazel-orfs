set file [open [file join $::env(WORK_HOME) "report.yaml"] "w"]
puts $file "bye"
close $file

set ::env(REPORTS_DIR) $::env(WORK_HOME)
source $::env(SCRIPTS_DIR)/save_images.tcl
