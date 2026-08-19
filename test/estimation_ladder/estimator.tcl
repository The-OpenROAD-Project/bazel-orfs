# Fast estimation script demonstrating multi-stage estimation in OpenROAD

set stage_name $::env(ESTIMATION_STAGE)
puts "Running estimation ladder step for stage: $stage_name"

source $::env(SCRIPTS_DIR)/load.tcl

# load_design automatically prefixes paths with $::env(RESULTS_DIR). 
# We need to strip this prefix from ODB_FILE.
set relative_odb [string map [list "$::env(RESULTS_DIR)/" ""] $::env(ODB_FILE)]

source_env_var_if_exists PLATFORM_TCL
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)

if { [file exists $::env(PLATFORM_DIR)/derate.tcl] } {
    source $::env(PLATFORM_DIR)/derate.tcl
}

if { [env_var_exists_and_non_empty LAYER_PARASITICS_FILE] } {
    source $::env(LAYER_PARASITICS_FILE)
} else {
    source $::env(PLATFORM_DIR)/setRC.tcl
}

set clock_period [get_property [get_clocks core_clock] period]
set min_period 0.0

catch {
    set reg2reg_group [sta::find_path_group "reg2reg"]
    if {$reg2reg_group ne ""} {
        # find_timing_paths -group expects the group name, not the pointer? Or just -group reg2reg
        # Just use report_checks to a variable and parse it if find_timing_paths is finicky.
        # Actually sta::worst_slack works for the network or we can just use sta::worst_slack without max/group
        
        # Let's just use the robust way: get worst slack overall since this is just a multiplier.
        set wns [sta::worst_slack -max]
        set min_period [expr {$clock_period - $wns}]
    }
}

if {$min_period == 0.0} {
    # Fallback to total WNS if the group is empty or missing
    set wns [sta::worst_slack -max]
    set min_period [expr {$clock_period - $wns}]
}

set fp [open $::env(OUTPUT_YAML) "w"]
puts $fp "stage: $stage_name"
puts $fp "clock_period: $min_period"
close $fp

puts "Wrote estimation metrics to $::env(OUTPUT_YAML)"
