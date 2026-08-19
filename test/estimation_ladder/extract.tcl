set design [file tail $::env(ODB_FILE)]
set sdc [file tail $::env(SDC_FILE)]
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file tail $::env(SDC_FILE)]

set paths [find_timing_paths -sort_by_slack -group_count 1000]

set max_slack -9999.0
set min_slack 9999.0
set valid_paths []

foreach path $paths {
    set sp [get_property $path startpoint]
    set ep [get_property $path endpoint]
    
    set sp_name [get_full_name $sp]
    set ep_name [get_full_name $ep]
    
    set slack [sta::format_time [[$path path] slack] 4]
    lappend valid_paths [list $sp_name $ep_name $slack]
    if {$slack > $max_slack} { set max_slack $slack }
    if {$slack < $min_slack} { set min_slack $slack }
}

set num_buckets 10
set step [expr {($max_slack - $min_slack) / $num_buckets}]
set selected_paths []

for {set i 0} {$i < $num_buckets} {incr i} {
    set target_slack [expr {$min_slack + ($i * $step)}]
    set best_path ""
    set best_diff 9999.0
    
    foreach pt $valid_paths {
        set slack [lindex $pt 2]
        set diff [expr {abs($slack - $target_slack)}]
        if {$diff < $best_diff} {
            set best_diff $diff
            set best_path $pt
        }
    }
    
    if {$best_path != ""} {
        lappend selected_paths $best_path
    }
}

if {[llength $selected_paths] == 0} { puts "ERROR: No paths found!"; exit 1 }

set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "\"runtime_ms\": 0,"
puts $fp "\"paths\": \["
set is_first 1
foreach pt $selected_paths {
    if {$is_first == 0} { puts $fp "," }
    set is_first 0
    puts -nonewline $fp "  {\"start\": \"[lindex $pt 0]\", \"end\": \"[lindex $pt 1]\", \"slack\": [lindex $pt 2]}"
}
puts $fp ""
puts $fp "\]"
puts $fp "}"
close $fp
exit 0
