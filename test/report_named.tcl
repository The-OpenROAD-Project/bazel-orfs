# Writes OUTPUT rather than a fixed filename, so several orfs_run targets in
# one package can each declare their own out.
set file [open [file join $::env(WORK_HOME) $::env(OUTPUT)] "w"]
puts $file "bye"
close $file
