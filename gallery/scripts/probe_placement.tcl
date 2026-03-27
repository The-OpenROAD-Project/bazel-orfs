# Probe placement: run a fast routability-driven global placement on the
# floorplan ODB, analyze density + RUDY, and emit placement-tips.tcl
# as create_blockage constraints for the real placement stage.
#
# This script is an orfs_run target that depends on floorplan and
# produces a .tcl file consumed by PRE_GLOBAL_PLACE_TCL.

# Load geometry + liberty (needed for set_dont_use), skip SDC/parasitics.
source $::env(SCRIPTS_DIR)/load.tcl
source_env_var_if_exists PLATFORM_TCL
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(RESULTS_DIR)/2_floorplan.odb

set block [ord::get_db_block]
set die [$block getDieArea]
set die_x1 [ord::dbu_to_microns [$die xMin]]
set die_y1 [ord::dbu_to_microns [$die yMin]]
set die_x2 [ord::dbu_to_microns [$die xMax]]
set die_y2 [ord::dbu_to_microns [$die yMax]]
set die_w [expr {$die_x2 - $die_x1}]
set die_h [expr {$die_y2 - $die_y1}]

puts "Die: [format {%.1f x %.1f} $die_w $die_h] um"

# --- Run a fast probe placement (routability-driven, no timing) ---
puts "\n=== Running probe global placement (routability-driven) ==="

if {[env_var_exists_and_non_empty DONT_USE_CELLS]} {
    set_dont_use $::env(DONT_USE_CELLS)
}

global_placement \
    -skip_io \
    -routability_driven \
    -density $::env(PLACE_DENSITY) \
    -pad_left $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) \
    -pad_right $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT)

puts "Probe placement complete."

# --- Analyze density + RUDY on probe result ---
set nx 8
set ny 8
set tile_w [expr {$die_w / $nx}]
set tile_h [expr {$die_h / $ny}]
set tile_area [expr {$tile_w * $tile_h}]

# Initialize grids
for {set iy 0} {$iy < $ny} {incr iy} {
    for {set ix 0} {$ix < $nx} {incr ix} {
        set cell_area($iy,$ix) 0.0
        set inst_count($iy,$ix) 0
        set rudy($iy,$ix) 0.0
    }
}

# Instance density
set insts [$block getInsts]
foreach inst $insts {
    set bbox [$inst getBBox]
    set cx [expr {([ord::dbu_to_microns [$bbox xMin]] + [ord::dbu_to_microns [$bbox xMax]]) / 2.0}]
    set cy [expr {([ord::dbu_to_microns [$bbox yMin]] + [ord::dbu_to_microns [$bbox yMax]]) / 2.0}]
    set ix [expr {min($nx - 1, int(($cx - $die_x1) / $tile_w))}]
    set iy [expr {min($ny - 1, int(($cy - $die_y1) / $tile_h))}]
    set w [expr {[ord::dbu_to_microns [$bbox xMax]] - [ord::dbu_to_microns [$bbox xMin]]}]
    set h [expr {[ord::dbu_to_microns [$bbox yMax]] - [ord::dbu_to_microns [$bbox yMin]]}]
    set cell_area($iy,$ix) [expr {$cell_area($iy,$ix) + $w * $h}]
    incr inst_count($iy,$ix)
}

# RUDY from net bounding boxes
set nets [$block getNets]
foreach net $nets {
    set iters [$net getITerms]
    set bters [$net getBTerms]
    if {[llength $iters] + [llength $bters] < 2} continue
    set sig_type [$net getSigType]
    if {$sig_type == "POWER" || $sig_type == "GROUND"} continue

    set min_x 1e30; set min_y 1e30; set max_x -1e30; set max_y -1e30
    set pin_count 0

    foreach iterm $iters {
        set inst [$iterm getInst]
        set bbox [$inst getBBox]
        set px [expr {([ord::dbu_to_microns [$bbox xMin]] + [ord::dbu_to_microns [$bbox xMax]]) / 2.0}]
        set py [expr {([ord::dbu_to_microns [$bbox yMin]] + [ord::dbu_to_microns [$bbox yMax]]) / 2.0}]
        if {$px < $min_x} {set min_x $px}; if {$py < $min_y} {set min_y $py}
        if {$px > $max_x} {set max_x $px}; if {$py > $max_y} {set max_y $py}
        incr pin_count
    }
    foreach bterm $bters {
        foreach pin [$bterm getBPins] {
            foreach box [$pin getBoxes] {
                set px [expr {([ord::dbu_to_microns [$box xMin]] + [ord::dbu_to_microns [$box xMax]]) / 2.0}]
                set py [expr {([ord::dbu_to_microns [$box yMin]] + [ord::dbu_to_microns [$box yMax]]) / 2.0}]
                if {$px < $min_x} {set min_x $px}; if {$py < $min_y} {set min_y $py}
                if {$px > $max_x} {set max_x $px}; if {$py > $max_y} {set max_y $py}
                incr pin_count
            }
        }
    }
    if {$pin_count < 2} continue

    set hpwl [expr {($max_x - $min_x) + ($max_y - $min_y)}]
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

# Find max RUDY for normalization
set max_rudy 0
for {set iy 0} {$iy < $ny} {incr iy} {
    for {set ix 0} {$ix < $nx} {incr ix} {
        if {$rudy($iy,$ix) > $max_rudy} {set max_rudy $rudy($iy,$ix)}
    }
}

# --- Report ---
puts "\n=== Probe placement density + RUDY (${nx}x${ny}) ==="
puts [format "%-4s %-4s %7s %8s %7s  %-s" Row Col Insts Dens% RUDY% Region]
puts "--------------------------------------------------------------"

set hot_regions {}
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

        # Flag tiles with high density OR high RUDY
        if {$density > 50.0 || $rudy_norm > 80.0} {
            lappend hot_regions [list $iy $ix $density $rudy_norm $region]
        }
    }
}

# --- Emit placement-tips.tcl ---
set outfile $::env(PLACEMENT_TIPS_OUT)
set f [open $outfile w]

puts $f "# Auto-generated placement tips from probe_placement.tcl"
puts $f "# Based on routability-driven probe of floorplan ODB."
puts $f "# Regions with >50% cell density get soft blockages to spread cells."
puts $f "#"
puts $f "# Die: [format {%.1f x %.1f} $die_w $die_h] um"
puts $f "# Instances: [llength $insts]"
puts $f "# Grid: ${nx}x${ny} tiles ([format {%.1f x %.1f} $tile_w $tile_h] um each)"
puts $f ""

set n_constraints 0
foreach hr $hot_regions {
    lassign $hr row col density rudy_pct region
    if {$density > 50.0} {
        set target [expr {int($density * 0.75)}]
        puts $f "# Row $row Col $col: [format {%.1f}  $density]% density, [format {%.0f} $rudy_pct]% RUDY"
        puts $f "create_blockage -region \{$region\} -max_density $target -soft"
        puts $f ""
        incr n_constraints
    }
}

if {$n_constraints == 0} {
    puts $f "# No hot regions detected — placement density is uniform."
    puts $f "# No constraints needed."
}

close $f
puts "\nWrote $n_constraints constraints to: $outfile"
puts "Done."
