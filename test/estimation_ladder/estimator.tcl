# Fast estimation script demonstrating multi-stage estimation in OpenROAD
set output_yaml [expr {[info exists env(OUTPUT_YAML)] ? $env(OUTPUT_YAML) : "estimate.yaml"}]
set stage_name [expr {[info exists env(ESTIMATION_STAGE)] ? $env(ESTIMATION_STAGE) : "unknown"}]

puts "Running estimation ladder step for stage: $stage_name"

# Extract minimum achievable clock period for the reg2reg path group
set clock_period [get_property [get_clocks core_clock] period]
set min_period 0.0

catch {
    set wns_reg2reg [sta::worst_slack -max -group reg2reg]
    set min_period [expr {$clock_period - $wns_reg2reg}]
}

set fp [open $output_yaml "w"]
puts $fp "stage: $stage_name"
puts $fp "clock_period: $min_period"
close $fp

puts "Wrote estimation metrics to $output_yaml"
