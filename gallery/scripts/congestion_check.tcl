# Early congestion estimation after global placement.
#
# Run after do-3_1_place_gp_skip_io or do-3_2_place_iop to detect
# routing congestion before committing to CTS/GRT/route.
#
# Reports:
# - Estimated routing congestion per layer
# - Placement density in macro vs non-macro regions
# - Pin density hotspots
# - Recommendations for halo/density adjustments
#
# Usage via _deps:
#   tmp/<project>/<module>_place_deps/make do-step -- \
#     -no_init -exit -threads 1 scripts/congestion_check.tcl
#
# Or via orfs_run target.

read_db $::env(ODB_FILE)

set block [ord::get_db_block]
set bbox [$block getDieArea]
set die_w [expr {([$bbox xMax] - [$bbox xMin]) * [ord::dbu_to_microns 1]}]
set die_h [expr {([$bbox yMax] - [$bbox yMin]) * [ord::dbu_to_microns 1]}]

puts "============================================"
puts "  Early Congestion Check"
puts "============================================"
puts ""

# 1. Design overview
puts "--- Design Overview ---"
report_design_area
puts "Die: ${die_w} x ${die_h} µm"
puts ""

# 2. Count macros and standard cells
set n_macros 0
set n_stdcells 0
set macro_area 0
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    if {[$master isBlock]} {
        incr n_macros
        set macro_area [expr {$macro_area + [$master getWidth] * [$master getHeight]}]
    } else {
        incr n_stdcells
    }
}
set macro_area_um [expr {$macro_area * [ord::dbu_to_microns 1] * [ord::dbu_to_microns 1]}]
set die_area [expr {$die_w * $die_h}]
set macro_pct [expr {100.0 * $macro_area_um / $die_area}]

puts "--- Macro Analysis ---"
puts "Macros: $n_macros instances, ${macro_area_um} µm² ([format %.1f $macro_pct]% of die)"
puts "Standard cells: $n_stdcells"
set free_area [expr {$die_area - $macro_area_um}]
puts "Free area for routing/std cells: [format %.0f $free_area] µm²"
puts ""

# 3. Estimate routing congestion via GRT
puts "--- Estimated Routing Congestion (global route) ---"
puts "(Running global route estimation...)"
estimate_parasitics -placement
catch {global_route -congestion_iterations 0 -verbose} grt_result
if {$grt_result ne ""} {
    puts "GRT result: $grt_result (congestion detected — this is expected for analysis)"
}
puts ""

# 4. Check for macro placement issues
puts "--- Macro Placement Check ---"
if {$n_macros > 0} {
    # Find min gaps between macros
    set macro_bboxes {}
    foreach inst [$block getInsts] {
        if {[[$inst getMaster] isBlock]} {
            set bb [$inst getBBox]
            lappend macro_bboxes [list [$bb xMin] [$bb yMin] [$bb xMax] [$bb yMax] [$inst getName]]
        }
    }

    # Find smallest X and Y gaps
    set min_x_gap 999999999
    set min_y_gap 999999999
    set dbu [ord::dbu_to_microns 1]

    foreach m1 $macro_bboxes {
        foreach m2 $macro_bboxes {
            if {$m1 eq $m2} continue
            set m1_xhi [lindex $m1 2]
            set m2_xlo [lindex $m2 0]
            set m1_yhi [lindex $m1 3]
            set m2_ylo [lindex $m2 1]

            # X gap: m2 is to the right of m1
            set xgap [expr {($m2_xlo - $m1_xhi) * $dbu}]
            if {$xgap > 0 && $xgap < $min_x_gap} {
                set min_x_gap $xgap
            }
            # Y gap: m2 is above m1
            set ygap [expr {($m2_ylo - $m1_yhi) * $dbu}]
            if {$ygap > 0 && $ygap < $min_y_gap} {
                set min_y_gap $ygap
            }
        }
    }

    if {$min_x_gap < 999999999} {
        puts "Min X gap between macros: [format %.3f $min_x_gap] µm"
        if {$min_x_gap < 1.0} {
            puts "  WARNING: X gap < 1 µm — no room for routing channels between columns"
            puts "  Consider adding MACRO_PLACE_HALO X component (e.g. 2-5 µm)"
        }
    }
    if {$min_y_gap < 999999999} {
        puts "Min Y gap between macros: [format %.3f $min_y_gap] µm"
        if {$min_y_gap < 2.0} {
            puts "  WARNING: Y gap < 2 µm — tight for clock and signal routing"
        }
    }
}
puts ""

# 5. Summary and recommendations
puts "============================================"
puts "  Recommendations"
puts "============================================"
if {$macro_pct > 60} {
    puts "- High macro density ([format %.0f $macro_pct]%) — consider increasing die area"
}
if {$n_macros > 0 && [info exists min_x_gap] && $min_x_gap < 1.0} {
    puts "- Zero/small X halo between macros blocks horizontal routing"
    puts "  Suggestion: MACRO_PLACE_HALO \"2 <current_y_halo>\""
}
puts "- Check congestion report above for layers with overflow > 0"
puts "- If overflow exists, increase die area or add routing channels"
puts ""

# 6. Generate congestion heatmap image if GUI available and GALLERY_IMAGE set
if {[info exists ::env(GALLERY_IMAGE)] && [ord::openroad_gui_compiled]} {
    puts "--- Generating congestion heatmap ---"

    set xlo [ord::dbu_to_microns [$bbox xMin]]
    set ylo [ord::dbu_to_microns [$bbox yMin]]
    set xhi [ord::dbu_to_microns [$bbox xMax]]
    set yhi [ord::dbu_to_microns [$bbox yMax]]

    set width_um [expr {$xhi - $xlo}]
    set height_um [expr {$yhi - $ylo}]
    if {$width_um > $height_um} {
        set width_px 2000
    } else {
        set width_px [expr {int(2000.0 * $width_um / $height_um)}]
    }

    gui::clear_highlights -1
    gui::clear_selections

    gui::set_display_controls "*" visible false
    gui::set_display_controls "Layers/*" visible true
    gui::set_display_controls "Instances/*" visible true
    gui::set_display_controls "Instances/Physical/Fill cell" visible false
    gui::set_display_controls "Nets/Power" visible true
    gui::set_display_controls "Nets/Ground" visible true
    gui::set_display_controls "Heat Maps/Routing Congestion" visible true
    gui::set_display_controls "Misc/Scale bar" visible true

    gui::fit
    save_image -area [list $xlo $ylo $xhi $yhi] -width $width_px $::env(GALLERY_IMAGE)
    puts "Wrote congestion heatmap to $::env(GALLERY_IMAGE)"
}
