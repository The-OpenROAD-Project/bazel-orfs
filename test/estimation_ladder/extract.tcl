source $::env(SCRIPTS_DIR)/load.tcl
source $::env(EXTRACT_LIB_TCL)
set odb_tail [file tail $::env(ODB_FILE)]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail

# The grt ODB is post-CTS: use the real clock tree and global-routing
# parasitics, as open.tcl's read_timing does for stage >= 5.
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing

set sample [extract_sample_paths]
set area [extract_design_area]

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
puts $fp "\"time_unit\": \"[sta::unit_scale_abbreviation time][sta::unit_suffix time]\","
puts $fp "\"clock_period\": [dict get $sample clock_period],"
puts $fp "[extract_ppa_json $area],"
puts $fp "\"stages\": \{"
set sfirst 1
foreach {k v} $stage_breakdown {
    if {$sfirst == 0} { puts $fp "," }
    set sfirst 0
    puts -nonewline $fp "  \"$k\": $v"
}
puts $fp ""
puts $fp "\},"
puts $fp "\"paths\": [extract_paths_json [dict get $sample paths]]"
puts $fp "}"
close $fp
exit 0
