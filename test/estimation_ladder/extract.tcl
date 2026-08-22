source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]

set clk [lindex [all_clocks] 0]
set clk_period [get_property $clk period]
set wns [sta::worst_slack -max]

set num_buckets 10
set step [expr {($clk_period - $wns) / double($num_buckets)}]
set selected_paths []

for {set i 0} {$i < $num_buckets} {incr i} {
    set b_min [expr {$wns + $i * $step}]
    set b_max [expr {$wns + ($i + 1) * $step}]
    
    set paths [find_timing_paths -slack_min $b_min -slack_max $b_max -sort_by_slack -group_count 1]
    if {[llength $paths] > 0} {
        set path [lindex $paths 0]
        set sp [get_property $path startpoint]
        set ep [get_property $path endpoint]
        set sp_name [get_full_name $sp]
        set ep_name [get_full_name $ep]
        set slack [sta::format_time [[$path path] slack] 4]
        lappend selected_paths [list $sp_name $ep_name $slack]
    }
}

if {[llength $selected_paths] < 5} {
    puts "ERROR: Too few valid timing path buckets found ([llength $selected_paths] < 5)!"
    exit 1
}

package require json::write

set path_json_entries []
foreach pt $selected_paths {
    lappend path_json_entries [json::write object \
        "start" [json::write string [lindex $pt 0]] \
        "end"   [json::write string [lindex $pt 1]] \
        "slack" [lindex $pt 2]]
}

set out_json [json::write object \
    "runtime_ms" 0 \
    "paths" [json::write array {*}$path_json_entries]]

set fp [open $::env(OUTPUT_JSON) w]
puts $fp $out_json
close $fp
exit 0
