source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $::env(ODB_FILE)]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail

# Find worst negative slack to define the bottom of the range
set wns_path [find_timing_paths -sort_by_slack -group_path_count 1]
if {[llength $wns_path] == 0} {
    puts "ERROR: No timing paths found!"
    exit 1
}
set wns [sta::format_time [[[lindex $wns_path 0] path] slack] 4]
set clk_period [get_property [lindex [get_clocks] 0] period]

puts "WNS: $wns, Clock Period: $clk_period"

set min_slack $wns
set max_slack [expr {$clk_period / 2.0}]
if {$max_slack < $min_slack} { set max_slack [expr {$min_slack + 1.0}] }

set num_buckets 10
set step [expr {($max_slack - $min_slack) / $num_buckets}]
set selected_paths []

for {set i 0} {$i < $num_buckets} {incr i} {
    set b_min [expr {$min_slack + ($i * $step)}]
    set b_max [expr {$min_slack + (($i + 1) * $step)}]
    
    set paths [find_timing_paths -slack_min $b_min -slack_max $b_max -sort_by_slack -group_path_count 1]
    if {[llength $paths] > 0} {
        set path [lindex $paths 0]
        set sp [get_property $path startpoint]
        set ep [get_property $path endpoint]
        set slack [sta::format_time [[$path path] slack] 4]
        set min_period [expr {$clk_period - $slack}]
        
        lappend selected_paths [list [get_full_name $sp] [get_full_name $ep] $min_period]
    }
}

if {[llength $selected_paths] < 5} {
    puts "ERROR: Found less than 5 unique timing paths across buckets ([llength $selected_paths]). Design is too trivial."
    exit 1
}

set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "\"runtime_ms\": 0,"
puts $fp "\"paths\": \["
set is_first 1
foreach pt $selected_paths {
    if {$is_first == 0} { puts $fp "," }
    set is_first 0
    puts -nonewline $fp "  {\"start\": \"[lindex $pt 0]\", \"end\": \"[lindex $pt 1]\", \"min_period\": [lindex $pt 2]}"
}
puts $fp ""
puts $fp "\]"
puts $fp "}"
close $fp
exit 0
