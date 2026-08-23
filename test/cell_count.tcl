# Idiomatic JSON serializer for simple flat dicts, since standard Tcl json/struct 
# packages are missing in the OpenROAD binary environment.
proc escape_json {str} {
    set escaped [string map { \" \\\" \\ \\\\ \/ \\/ \b \\b \f \\f \n \\n \r \\r \t \\t } $str]
    return "\"$escaped\""
}
proc json_dict {dict_args} {
    set items {}
    foreach {k v} $dict_args {
        # Treat as raw number if it matches a float/int, else quote it
        if {[string is double -strict $v]} {
            lappend items "[escape_json $k]: $v"
        } else {
            lappend items "[escape_json $k]: [escape_json $v]"
        }
    }
    return "\{ [join $items ", "] \}"
}

# Load the full environment (liberty files, tech LEF, SDC, etc.)
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

# Run the reports. Because there are no catch blocks, this will fail early 
# if the environment is incorrectly configured.
report_clock_skew
report_tns
report_cell_usage

# Extract actual metrics using OpenROAD APIs
set tns [sta::total_negative_slack]
set wns [sta::worst_slack -max]
set cell_count [llength [[ord::get_db_block] getInsts]]

puts "Mock script completed successfully!"

# Write the metrics to METRICS_OUT (must be defined or it fails early!)
set payload [json_dict [list density $::env(PLACE_DENSITY) tns $tns wns $wns cell_count $cell_count]]

set fd [open $::env(METRICS_OUT) w]
puts $fd $payload
close $fd
puts "Wrote metrics to $::env(METRICS_OUT)"
