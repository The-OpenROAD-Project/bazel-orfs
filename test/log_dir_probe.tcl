# LOG_DIR must name the log directory of the flow the src stage belongs to
# — the one every stage's log and metrics json accumulates in — whatever
# package and variant the consuming orfs_run has. Writes the whole
# accumulated set so the checking test compares it against the expected
# one rather than settling for "not empty".
# Kept to the mock-openroad Tcl subset so this runs in seconds in CI.
set log_dir $::env(LOG_DIR)
set accumulated [lsort [glob -nocomplain -directory $log_dir {[1-9]_*}]]

set f [open $::env(OUTPUT) w]
foreach path $accumulated {
  puts $f [file tail $path]
}
close $f

if {[llength $accumulated] == 0} {
  error "no accumulated stage logs in LOG_DIR=$log_dir"
}
