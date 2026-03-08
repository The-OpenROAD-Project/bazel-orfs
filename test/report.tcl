set file [open [file join $::env(WORK_HOME) "report.yaml"] "w"]
puts $file "bye"
close $file
