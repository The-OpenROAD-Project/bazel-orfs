source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $::env(ODB_FILE)]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail

# The grt ODB is post-CTS: use the real clock tree and global-routing
# parasitics, as open.tcl's read_timing does for stage >= 5.
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing

# The reg2reg path group is defined by the platform SDC. Note that a
# "register" can be a macro, not just a flip-flop.
set wns_path [find_timing_paths -path_group reg2reg -sort_by_slack -group_path_count 1]
if {[llength $wns_path] == 0} {
    puts "ERROR: No reg2reg timing paths found!"
    exit 1
}
set wns [get_property [lindex $wns_path 0] slack]
set clk_period [get_property [lindex [get_clocks] 0] period]

puts "WNS: $wns, Clock Period: $clk_period"

# Sample the worst 25% of the min_period range. min_period = clk_period -
# slack, so the window [0.75 * max_period, max_period] maps to slacks in
# [wns, wns + 0.25 * max_period].
set max_period [expr {$clk_period - $wns}]
set num_buckets 10
set paths_per_bucket 10
set step [expr {0.25 * $max_period / $num_buckets}]
set selected_paths []
set seen [dict create]

for {set i 0} {$i < $num_buckets} {incr i} {
    set b_min [expr {$wns + ($i * $step)}]
    set b_max [expr {$wns + (($i + 1) * $step)}]

    set paths [find_timing_paths -path_group reg2reg \
        -slack_min $b_min -slack_max $b_max \
        -sort_by_slack -group_path_count $paths_per_bucket]
    foreach path $paths {
        set sp [get_full_name [get_property $path startpoint]]
        set ep [get_full_name [get_property $path endpoint]]
        if {[dict exists $seen "$sp|$ep"]} {
            continue
        }
        dict set seen "$sp|$ep" 1
        set slack [get_property $path slack]
        set min_period [expr {$clk_period - $slack}]
        lappend selected_paths [list $sp $ep $min_period]
    }
}

if {[llength $selected_paths] < 20} {
    puts "ERROR: Found only [llength $selected_paths] unique reg2reg paths in the worst-25% window. Design is too trivial."
    exit 1
}
puts "Sampled [llength $selected_paths] reg2reg paths."

# Ground truth runtime: the cost of producing the grt ODB beyond
# synthesis, summed from the floorplan..grt stage logs (synthesis is the
# common starting point for both the ground truth and the estimator).
set gt_runtime_s 0.0
set stage_breakdown [dict create]
set stage_logs [lsort [glob -directory $::env(LOG_DIR) {[2-5]_*.log}]]
foreach stage_log $stage_logs {
    set lfp [open $stage_log r]
    set content [read $lfp]
    close $lfp
    if {![regexp {Elapsed time: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\[h:\]min:sec} $content -> hours mins secs]} {
        error "No elapsed time found in $stage_log"
    }
    if {$hours eq ""} { set hours 0 }
    set stage_s [expr {$hours * 3600 + $mins * 60 + $secs}]
    set gt_runtime_s [expr {$gt_runtime_s + $stage_s}]
    # Per stage, not just the total: "the flow takes 668s" says nothing
    # about what the estimator is declining to run, and it turns out over
    # half of it is one stage.
    dict set stage_breakdown [file rootname [file tail $stage_log]] $stage_s
}
foreach {k v} $stage_breakdown { puts "GT_STAGE $k $v" }
puts "Ground truth flow runtime: $gt_runtime_s s ([llength $stage_logs] stages)"

set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "\"runtime_s\": $gt_runtime_s,"
puts $fp "\"stages\": \{"
set sfirst 1
foreach {k v} $stage_breakdown {
    if {$sfirst == 0} { puts $fp "," }
    set sfirst 0
    puts -nonewline $fp "  \"$k\": $v"
}
puts $fp ""
puts $fp "\},"
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
