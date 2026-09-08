# What one point on the size curve actually cost, and what it bought.
#
# The design's dimensions are a measured choice, not a taste: it has to
# be small enough to sit inside an OpenROAD edit/measure loop and big
# enough that wire delay sets the period. This probe reports both halves
# for one variant so the curve can be read rather than argued about --
# instance count and area on one side, per-stage wall time on the other.
#
# Runtime is read out of the stage logs rather than timed around the
# build, because a cached stage costs nothing to rebuild and would
# otherwise report as an improvement.

# RESULTS_DIR belongs to the package declaring this run, not to the one
# that built the src, so stage the src's artifacts in before load.tcl
# looks for them.
source $::env(STAGE_SRC_TCL)

source $::env(SCRIPTS_DIR)/load.tcl
source $::env(EXTRACT_LIB_TCL)
set odb_tail [file tail $stage_src_staged]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail

set area [extract_design_area]
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set die [$block getDieArea]
set core [$block getCoreArea]
set die_w [expr { ([$die xMax] - [$die xMin]) * 1.0 / $dbu }]
set die_h [expr { ([$die yMax] - [$die yMin]) * 1.0 / $dbu }]
set core_w [expr { ([$core xMax] - [$core xMin]) * 1.0 / $dbu }]
set core_h [expr { ([$core yMax] - [$core yMin]) * 1.0 / $dbu }]
set core_um2 [expr { $core_w * $core_h }]
set stdcell_um2 [dict get $area stdcell_um2]
set utilization [expr { $core_um2 > 0 ? 100.0 * $stdcell_um2 / $core_um2 : 0.0 }]

# Per-stage wall time, same parse as test/estimation_ladder/extract.tcl.
#
# `*_metrics.log` is excluded by name rather than by tolerating a missing
# elapsed line. A metrics log is a report emitted inside a stage, not a
# stage, and it carries no elapsed time -- so a parser that shrugged at
# "no elapsed line" would also shrug at a real stage log that failed to
# finish, and quietly under-report the cost of the point. Naming the
# exception keeps the missing-elapsed case an error.
set total_s 0.0
set stages [dict create]
set stage_logs {}
foreach stage_log [lsort [glob -nocomplain -directory $::env(LOG_DIR) {[1-6]_*.log}]] {
    if { [string match "*_metrics" [file rootname [file tail $stage_log]]] } {
        continue
    }
    lappend stage_logs $stage_log
}
foreach stage_log $stage_logs {
    set lfp [open $stage_log r]
    set content [read $lfp]
    close $lfp
    if { ![regexp {Elapsed time: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\[h:\]min:sec} \
        $content -> hours mins secs] } {
        error "no elapsed time in $stage_log"
    }
    if { $hours eq "" } { set hours 0 }
    set stage_s [expr { $hours * 3600 + $mins * 60 + $secs }]
    set total_s [expr { $total_s + $stage_s }]
    dict set stages [file rootname [file tail $stage_log]] $stage_s
}

# A leaf whose logs are absent measures nothing; say so rather than
# reporting a zero-second flow.
if { [dict size $stages] == 0 } {
    error "no stage logs under $::env(LOG_DIR): runtime is unmeasured"
}

puts "SIZE stdcells=[dict get $area num_stdcells] macros=[dict get $area num_macros]\
 stdcell_um2=$stdcell_um2 core=${core_w}x${core_h} util=${utilization}% total_s=$total_s"
foreach {k v} $stages { puts "SIZE_STAGE $k $v" }

set rows {}
foreach {k v} $stages {
    lappend rows [format {"%s": %g} $k $v]
}
set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"num_stdcells\": [dict get $area num_stdcells],"
puts $fp "  \"num_macros\": [dict get $area num_macros],"
puts $fp "  \"stdcell_um2\": $stdcell_um2,"
puts $fp "  \"die_width_um\": $die_w,"
puts $fp "  \"die_height_um\": $die_h,"
puts $fp "  \"core_width_um\": $core_w,"
puts $fp "  \"core_area_um2\": $core_um2,"
puts $fp "  \"core_height_um\": $core_h,"
puts $fp "  \"utilization_percent\": $utilization,"
puts $fp "  \"total_runtime_s\": $total_s,"
puts $fp "  \"stages\": \{[join $rows ", "]\}"
puts $fp "}"
close $fp
exit 0
