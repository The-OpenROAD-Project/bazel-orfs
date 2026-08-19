# Fast estimation script demonstrating multi-stage estimation in OpenROAD
set output_yaml [expr {[info exists env(OUTPUT_YAML)] ? $env(OUTPUT_YAML) : "estimate.yaml"}]
set stage_name [expr {[info exists env(ESTIMATION_STAGE)] ? $env(ESTIMATION_STAGE) : "unknown"}]

puts "Running estimation ladder step for stage: $stage_name"

# Extract basic timing metrics if timing graph is loaded
set wns "0.0"
set tns "0.0"
catch {
    set wns [sta::worst_slack -max]
    set tns [sta::total_negative_slack -max]
}

set fp [open $output_yaml "w"]
puts $fp "stage: $stage_name"
puts $fp "wns: $wns"
puts $fp "tns: $tns"
close $fp

puts "Wrote estimation metrics to $output_yaml"
