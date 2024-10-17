source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc

set paths [find_timing_paths -path_group reg2reg -sort_by_slack -group_count 1]
set path [lindex $paths 0]
set slack [get_property $path slack]

set fp [open $::env(OUTFILE) w]
puts $fp "slack: $slack"
close $fp
