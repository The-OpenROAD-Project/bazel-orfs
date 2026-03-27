# Analyze routing results — DRC violations with locations + convergence.
#
# Loads routed ODB, runs check_drc, reports violation types and
# locations, generates DRC heatmap image.
#
# Run via _deps make run after route completes.

source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_2_route.odb 5_1_grt.sdc

puts "============================================"
puts "  Route DRC Analysis"
puts "============================================"

report_design_area

# Run DRC
set_thread_count [exec nproc]
set drc_count [check_drc -output_file /tmp/drc_details.rpt]
puts "Total DRC violations: $drc_count"

# Parse the DRC report for violation types and locations
if {[file exists /tmp/drc_details.rpt]} {
    set f [open /tmp/drc_details.rpt r]
    set content [read $f]
    close $f

    # Count violations by type
    set type_counts [dict create]
    foreach line [split $content "\n"] {
        if {[regexp {violation type: (.+)} $line -> vtype]} {
            dict incr type_counts $vtype
        }
    }

    puts "\nViolation types:"
    dict for {vtype count} $type_counts {
        puts "  $vtype: $count"
    }

    # Count violations by region (quadrant of die)
    set block [ord::get_db_block]
    set bbox [$block getDieArea]
    set mid_x [expr {([$bbox xMin] + [$bbox xMax]) / 2}]
    set mid_y [expr {([$bbox yMin] + [$bbox yMax]) / 2}]

    set q_tl 0; set q_tr 0; set q_bl 0; set q_br 0
    foreach line [split $content "\n"] {
        if {[regexp {\((\d+), (\d+)\)} $line -> x y]} {
            if {$x < $mid_x && $y >= $mid_y} { incr q_tl }
            if {$x >= $mid_x && $y >= $mid_y} { incr q_tr }
            if {$x < $mid_x && $y < $mid_y} { incr q_bl }
            if {$x >= $mid_x && $y < $mid_y} { incr q_br }
        }
    }
    puts "\nViolations by quadrant:"
    puts "  Top-left: $q_tl  Top-right: $q_tr"
    puts "  Bot-left: $q_bl  Bot-right: $q_br"
}

puts "\n============================================"
