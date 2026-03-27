# Analyze placement density and estimated routing congestion (RUDY-based).
#
# Loads a placement ODB, computes per-tile instance density and
# estimates RUDY (Rectangular Uniform wire DensitY) congestion from
# net bounding boxes. Outputs suggested create_blockage constraints
# for placement-tips.tcl.
#
# Works on any stage ODB (place, cts, grt). No GRT run needed.

source $::env(SCRIPTS_DIR)/load.tcl

# Accept any stage ODB — check what's available
foreach stage {3_5_place_dp 3_3_place_gp 4_1_cts 5_1_grt} {
    set odb "$::env(RESULTS_DIR)/${stage}.odb"
    set sdc_candidates [list \
        "$::env(RESULTS_DIR)/${stage}.sdc" \
        "$::env(RESULTS_DIR)/2_floorplan.sdc"]
    if {[file exists $odb]} {
        foreach sdc $sdc_candidates {
            if {[file exists $sdc]} {
                puts "Loading: $odb + $sdc"
                load_design [file tail $odb] [file tail $sdc]
                break
            }
        }
        break
    }
}

set block [ord::get_db_block]
set tech [ord::get_db_tech]
set die [$block getDieArea]
set die_x1 [ord::dbu_to_microns [$die xMin]]
set die_y1 [ord::dbu_to_microns [$die yMin]]
set die_x2 [ord::dbu_to_microns [$die xMax]]
set die_y2 [ord::dbu_to_microns [$die yMax]]
set die_w [expr {$die_x2 - $die_x1}]
set die_h [expr {$die_y2 - $die_y1}]

puts "Die area: [format {%.1f %.1f %.1f %.1f} $die_x1 $die_y1 $die_x2 $die_y2] um"
puts "Die size: [format {%.1f x %.1f} $die_w $die_h] um"

# --- Grid setup ---
set nx 8
set ny 8
set tile_w [expr {$die_w / $nx}]
set tile_h [expr {$die_h / $ny}]

# --- Pass 1: Instance density per tile ---
set insts [$block getInsts]
puts "\nTotal instances: [llength $insts]"

# Initialize grids
for {set iy 0} {$iy < $ny} {incr iy} {
    for {set ix 0} {$ix < $nx} {incr ix} {
        set cell_area($iy,$ix) 0.0
        set inst_count($iy,$ix) 0
        set rudy($iy,$ix) 0.0
    }
}

# Count instances per tile
foreach inst $insts {
    set bbox [$inst getBBox]
    set cx [expr {([ord::dbu_to_microns [$bbox xMin]] + [ord::dbu_to_microns [$bbox xMax]]) / 2.0}]
    set cy [expr {([ord::dbu_to_microns [$bbox yMin]] + [ord::dbu_to_microns [$bbox yMax]]) / 2.0}]
    set ix [expr {int(($cx - $die_x1) / $tile_w)}]
    set iy [expr {int(($cy - $die_y1) / $tile_h)}]
    if {$ix >= $nx} { set ix [expr {$nx - 1}] }
    if {$iy >= $ny} { set iy [expr {$ny - 1}] }
    set w [expr {[ord::dbu_to_microns [$bbox xMax]] - [ord::dbu_to_microns [$bbox xMin]]}]
    set h [expr {[ord::dbu_to_microns [$bbox yMax]] - [ord::dbu_to_microns [$bbox yMin]]}]
    set cell_area($iy,$ix) [expr {$cell_area($iy,$ix) + $w * $h}]
    incr inst_count($iy,$ix)
}

# --- Pass 2: RUDY (Rectangular Uniform wire DensitY) ---
# For each net, distribute wire density uniformly across its bounding box.
# RUDY ≈ (HPWL / bbox_area) spread across tiles in the bbox.
set nets [$block getNets]
puts "Total nets: [llength $nets]"

foreach net $nets {
    set iters [$net getITerms]
    set bters [$net getBTerms]
    if {[llength $iters] + [llength $bters] < 2} continue
    # Skip power/ground
    set sig_type [$net getSigType]
    if {$sig_type == "POWER" || $sig_type == "GROUND"} continue

    # Compute net bounding box from pin positions
    set min_x 1e30
    set min_y 1e30
    set max_x -1e30
    set max_y -1e30
    set pin_count 0

    foreach iterm $iters {
        set inst [$iterm getInst]
        set bbox [$inst getBBox]
        set px [expr {([ord::dbu_to_microns [$bbox xMin]] + [ord::dbu_to_microns [$bbox xMax]]) / 2.0}]
        set py [expr {([ord::dbu_to_microns [$bbox yMin]] + [ord::dbu_to_microns [$bbox yMax]]) / 2.0}]
        if {$px < $min_x} { set min_x $px }
        if {$py < $min_y} { set min_y $py }
        if {$px > $max_x} { set max_x $px }
        if {$py > $max_y} { set max_y $py }
        incr pin_count
    }
    foreach bterm $bters {
        set pins [$bterm getBPins]
        foreach pin $pins {
            set boxes [$pin getBoxes]
            foreach box $boxes {
                set px [expr {([ord::dbu_to_microns [$box xMin]] + [ord::dbu_to_microns [$box xMax]]) / 2.0}]
                set py [expr {([ord::dbu_to_microns [$box yMin]] + [ord::dbu_to_microns [$box yMax]]) / 2.0}]
                if {$px < $min_x} { set min_x $px }
                if {$py < $min_y} { set min_y $py }
                if {$px > $max_x} { set max_x $px }
                if {$py > $max_y} { set max_y $py }
                incr pin_count
            }
        }
    }

    if {$pin_count < 2} continue

    # HPWL
    set hpwl [expr {($max_x - $min_x) + ($max_y - $min_y)}]
    set bbox_w [expr {max($max_x - $min_x, $tile_w * 0.1)}]
    set bbox_h [expr {max($max_y - $min_y, $tile_h * 0.1)}]
    set bbox_area [expr {$bbox_w * $bbox_h}]

    # Distribute RUDY across tiles covered by net bbox
    set ix1 [expr {max(0, int(($min_x - $die_x1) / $tile_w))}]
    set iy1 [expr {max(0, int(($min_y - $die_y1) / $tile_h))}]
    set ix2 [expr {min($nx - 1, int(($max_x - $die_x1) / $tile_w))}]
    set iy2 [expr {min($ny - 1, int(($max_y - $die_y1) / $tile_h))}]

    set n_tiles [expr {max(1, ($ix2 - $ix1 + 1) * ($iy2 - $iy1 + 1))}]
    set rudy_per_tile [expr {$hpwl / $n_tiles}]

    for {set iy $iy1} {$iy <= $iy2} {incr iy} {
        for {set ix $ix1} {$ix <= $ix2} {incr ix} {
            set rudy($iy,$ix) [expr {$rudy($iy,$ix) + $rudy_per_tile}]
        }
    }
}

# --- Report ---
set tile_area [expr {$tile_w * $tile_h}]

puts "\n=== Placement density + RUDY grid (${nx}x${ny}) ==="
puts [format "%-4s %-4s %7s %8s %7s  %-s" Row Col Insts Dens% RUDY Region]
puts "--------------------------------------------------------------"

set hot_density {}
set hot_rudy {}
set max_rudy 0
for {set iy 0} {$iy < $ny} {incr iy} {
    for {set ix 0} {$ix < $nx} {incr ix} {
        if {$rudy($iy,$ix) > $max_rudy} { set max_rudy $rudy($iy,$ix) }
    }
}

for {set iy 0} {$iy < $ny} {incr iy} {
    for {set ix 0} {$ix < $nx} {incr ix} {
        set density [expr {$tile_area > 0 ? ($cell_area($iy,$ix) / $tile_area) * 100.0 : 0}]
        set rudy_norm [expr {$max_rudy > 0 ? $rudy($iy,$ix) / $max_rudy * 100.0 : 0}]
        set tx1 [expr {$die_x1 + $ix * $tile_w}]
        set ty1 [expr {$die_y1 + $iy * $tile_h}]
        set tx2 [expr {$tx1 + $tile_w}]
        set ty2 [expr {$ty1 + $tile_h}]
        set region [format {%.1f %.1f %.1f %.1f} $tx1 $ty1 $tx2 $ty2]
        puts [format "%-4d %-4d %7d %8.1f %7.0f  %s" $iy $ix $inst_count($iy,$ix) $density $rudy_norm $region]

        if {$density > 50.0} {
            lappend hot_density [list $iy $ix $density $region]
        }
        if {$rudy_norm > 80.0} {
            lappend hot_rudy [list $iy $ix $rudy_norm $region]
        }
    }
}

# --- Top module clusters ---
puts "\n=== Top instance prefixes by count ==="
set prefix_count [dict create]
foreach inst $insts {
    set name [$inst getName]
    set parts [split $name "/"]
    set prefix [expr {[llength $parts] > 1 ? [lindex $parts 0] : "(top-level)"}]
    dict incr prefix_count $prefix
}
set sorted {}
dict for {k v} $prefix_count { lappend sorted [list $k $v] }
set sorted [lsort -integer -decreasing -index 1 $sorted]
puts [format "%4s %-40s %8s" "#" Prefix Insts]
set i 0
foreach entry [lrange $sorted 0 14] {
    puts [format "%4d %-40s %8d" [incr i] [lindex $entry 0] [lindex $entry 1]]
}

# --- Suggested constraints ---
puts "\n=== Suggested placement-tips.tcl ==="
puts "# Auto-generated from analyze_congestion.tcl"
puts "# Review and curate before committing.\n"

if {[llength $hot_density] > 0} {
    puts "# --- Dense regions (cell density > 50%) ---"
    foreach hr $hot_density {
        lassign $hr row col density region
        set target [expr {int($density * 0.75)}]
        puts "# Row $row Col $col: ${density}% cell density"
        puts "create_blockage -region \{$region\} -max_density $target -soft"
    }
}

if {[llength $hot_rudy] > 0} {
    puts "\n# --- High RUDY regions (wire density > 80% of peak) ---"
    puts "# These regions will likely congest during GRT."
    puts "# Consider: lower density blockage, or spread connected modules."
    foreach hr $hot_rudy {
        lassign $hr row col rudy_pct region
        puts "# Row $row Col $col: ${rudy_pct}% of peak RUDY"
    }
}

puts "\nDone."
