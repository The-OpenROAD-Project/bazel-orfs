set stage_name $::env(ESTIMATION_STAGE)
puts "Running estimation ladder step for stage: $stage_name"

source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/load.tcl

if { [info exists ::env(PLATFORM_DIR)] && [file exists $::env(PLATFORM_DIR)/platform.tcl] } {
    source $::env(PLATFORM_DIR)/platform.tcl
}

load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]

if {$stage_name != "grt_true"} {
    if {$stage_name != "synth"} {
        puts "Running floorplan..."
        if {[info exists ::env(DIE_AREA)]} { unset ::env(DIE_AREA) }
        source $::env(SCRIPTS_DIR)/floorplan.tcl
        
        if {![info exists ::env(IO_ROUTING_LAYER)]} { set ::env(IO_ROUTING_LAYER) "M2" }
        place_pins -hor_layers M2 -ver_layers M3
        
        if {$stage_name != "floorplan"} {
            puts "Sourcing global_place.tcl..."
            set ::env(GPL_TIMING_DRIVEN) 1
            set ::env(GPL_ROUTABILITY_DRIVEN) 1
            set ::env(DONT_BUFFER_PORTS) 0
            if {![info exists ::env(MIN_PLACE_STEP_COEF)]} { set ::env(MIN_PLACE_STEP_COEF) "0.95" }
            if {![info exists ::env(MAX_PLACE_STEP_COEF)]} { set ::env(MAX_PLACE_STEP_COEF) "1.05" }
            if {![info exists ::env(PLACE_DENSITY)]} { set ::env(PLACE_DENSITY) "0.6" }
            if {![info exists ::env(PAD_LEFT)]} { set ::env(PAD_LEFT) "0" }
            if {![info exists ::env(PAD_RIGHT)]} { set ::env(PAD_RIGHT) "0" }
            if {![info exists ::env(MACRO_PLACEMENT_FILE)]} { set ::env(MACRO_PLACEMENT_FILE) "" }
            if {![info exists ::env(PLACE_HALO)]} { set ::env(PLACE_HALO) "0" }
            # Add CLUSTER_FLOPS for ASAP7 placement checks
            if {![info exists ::env(CLUSTER_FLOPS)]} { set ::env(CLUSTER_FLOPS) 0 }
            
            source $::env(SCRIPTS_DIR)/global_place.tcl
            
            if {$stage_name != "place"} {
                puts "Running fast global_route (2 iterations)..."
                global_route -congestion_iterations 2
            }
        }
    }
}

if {$stage_name == "synth"} {
    puts "Skipping parasitics estimation for synth (ideal wires)"
} elseif {$stage_name == "grt" || $stage_name == "grt_true"} {
    puts "Estimating parasitics: global_routing"
    estimate_parasitics -global_routing
} else {
    puts "Estimating parasitics: placement"
    estimate_parasitics -placement
}

set clock_period [get_property [get_clocks core_clock] period]

set paths [find_timing_paths -sort_by_slack]
set slack 0.0

foreach path $paths {
    set sp [get_property $path startpoint]
    set ep [get_property $path endpoint]
    
    set sp_name [get_property $sp name]
    set ep_name [get_property $ep name]
    
    if { [string match "*_reg*" $sp_name] && [string match "*_reg*" $ep_name] } {
        set slack [sta::format_time [[$path path] slack] 4]
        break
    }
}

if {$slack == 0.0} {
    set slack [sta::format_time [[[lindex $paths 0] path] slack] 4]
}

set min_period [expr {$clock_period - $slack}]

set fp [open $::env(OUTPUT_YAML) "w"]
puts $fp "stage: $stage_name"
puts $fp "clock_period: [format "%.2f" $min_period]"
close $fp

puts "Wrote estimation metrics to $::env(OUTPUT_YAML)"
