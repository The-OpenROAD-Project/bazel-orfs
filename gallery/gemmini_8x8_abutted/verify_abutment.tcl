# Verify macro abutment in top-level floorplan.
#
# Checks that Tile macros form an 8×8 grid with zero X gap (abutment)
# and ~5 µm Y gap (clock routing channel).
#
# Run via: bazelisk run //gemmini_8x8_abutted:verify_abutment

set db [ord::get_db]
set block [[$db getChip] getBlock]
set dbu [ord::dbu_to_microns 1]

# Collect all macro instances
set macros {}
foreach inst [$block getInsts] {
    if {[[$inst getMaster] isMacro]} {
        set bbox [$inst getBBox]
        set x [expr {[$bbox xMin] * $dbu}]
        set y [expr {[$bbox yMin] * $dbu}]
        set w [expr {([$bbox xMax] - [$bbox xMin]) * $dbu}]
        set h [expr {([$bbox yMax] - [$bbox yMin]) * $dbu}]
        lappend macros [list [$inst getName] $x $y $w $h]
    }
}

set n_macros [llength $macros]
puts "Found $n_macros macros"

if {$n_macros != 64} {
    puts "WARNING: expected 64 macros (8×8), got $n_macros"
}

if {$n_macros == 0} {
    puts "FAIL: no macros found"
    exit 1
}

# Check all macros have identical dimensions
set first_w [lindex [lindex $macros 0] 3]
set first_h [lindex [lindex $macros 0] 4]
set dim_errors 0
foreach m $macros {
    set w [lindex $m 3]
    set h [lindex $m 4]
    if {abs($w - $first_w) > 0.001 || abs($h - $first_h) > 0.001} {
        puts "ERROR: macro [lindex $m 0] has size ${w}×${h}, expected ${first_w}×${first_h}"
        incr dim_errors
    }
}
puts "Macro dimensions: ${first_w} × ${first_h} µm"

# Sort macros into grid by Y then X
set sorted [lsort -real -index 2 [lsort -real -index 1 $macros]]

# Group into rows by Y coordinate (tolerance 0.1 µm)
set rows {}
set current_row {}
set current_y -999
foreach m $sorted {
    set y [lindex $m 2]
    if {abs($y - $current_y) > 0.1} {
        if {[llength $current_row] > 0} {
            lappend rows [lsort -real -index 1 $current_row]
        }
        set current_row {}
        set current_y $y
    }
    lappend current_row $m
}
if {[llength $current_row] > 0} {
    lappend rows [lsort -real -index 1 $current_row]
}

set n_rows [llength $rows]
puts "Grid: $n_rows rows"
foreach row $rows {
    puts "  Row at Y=[format %.2f [lindex [lindex $row 0] 2]]: [llength $row] macros"
}

# Check X gaps within each row (should be 0 for abutment)
set abutment_errors 0
puts ""
puts "Checking X abutment (zero gap between columns)..."
foreach row $rows {
    for {set i 0} {$i < [llength $row] - 1} {incr i} {
        set m1 [lindex $row $i]
        set m2 [lindex $row [expr {$i + 1}]]
        set x1_right [expr {[lindex $m1 1] + [lindex $m1 3]}]
        set x2_left [lindex $m2 1]
        set gap [expr {$x2_left - $x1_right}]
        if {abs($gap) > 0.01} {
            puts "  ERROR: gap=[format %.3f $gap]µm between [lindex $m1 0] and [lindex $m2 0]"
            incr abutment_errors
        }
    }
}

# Check Y gaps between rows (should be ~5 µm for clock channel)
puts ""
puts "Checking Y gaps between rows (expect ~5 µm)..."
set y_gap_errors 0
for {set i 0} {$i < $n_rows - 1} {incr i} {
    set row_bot [lindex $rows $i]
    set row_top [lindex $rows [expr {$i + 1}]]
    set y1_top [expr {[lindex [lindex $row_bot 0] 2] + [lindex [lindex $row_bot 0] 4]}]
    set y2_bot [lindex [lindex $row_top 0] 2]
    set gap [expr {$y2_bot - $y1_top}]
    puts "  Row $i → [expr {$i + 1}]: gap=[format %.2f $gap] µm"
    if {$gap < 1.0} {
        puts "  WARNING: Y gap too small for clock routing"
        incr y_gap_errors
    }
}

puts ""
set total_errors [expr {$dim_errors + $abutment_errors + $y_gap_errors}]
if {$total_errors == 0} {
    puts "PASS: Abutment verification passed ($n_macros macros, $n_rows rows, zero X gap)"
} else {
    puts "FAIL: $total_errors errors found"
}
