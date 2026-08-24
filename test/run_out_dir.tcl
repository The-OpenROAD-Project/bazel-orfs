# Exercises orfs_run's out_dir: the script decides at runtime what files
# to put in $RUN_OUTPUT_DIR. Kept to the mock-openroad Tcl subset so the
# capability is tested fast in CI.
set dir $::env(RUN_OUTPUT_DIR)

set f [open $dir/alpha.txt w]
puts $f "alpha"
close $f

set f [open $dir/beta.txt w]
puts $f "beta"
close $f
