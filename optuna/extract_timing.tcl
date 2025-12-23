source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc

# Get clock period
set clocks [get_clocks]
set clock [lindex $clocks 0]
set clock_period [get_property $clock period]

# Get worst slack
set paths [find_timing_paths -path_group reg2reg -sort_by_slack -group_path_count 1]
set path [lindex $paths 0]
set slack [get_property $path slack]

# Calculate actual achievable clock period
# achievable_period = clock_period - slack
set achievable_period [expr {$clock_period - $slack}]

set fp [open $::env(OUTFILE) w]
puts $fp "clock_period: $clock_period"
puts $fp "slack: $slack"
puts $fp "achievable_period: $achievable_period"
close $fp
