# Place 64 Tile macros in an 8×8 grid with routing by abutment.
# X pitch = tile width (zero gap), Y pitch = tile height + channel.

set db [ord::get_db]
set block [[$db getChip] getBlock]

# Find first Tile macro to get dimensions
set first_inst ""
foreach inst [$block getInsts] {
    if {[[$inst getMaster] isBlock]} {
        set first_inst $inst
        break
    }
}

if {$first_inst eq ""} {
    puts "ERROR: no macro instances found"
    return
}

set master [$first_inst getMaster]
set tile_w [ord::dbu_to_microns [$master getWidth]]
set tile_h [ord::dbu_to_microns [$master getHeight]]

puts "Tile dimensions: ${tile_w} x ${tile_h} µm"

# Grid parameters (must match BUILD.bazel CORE_AREA)
# Center array in core, snapped to N*pitch (no track offset!)
# pin_x = 0.012 + M*pitch, macro_origin = N*pitch
# absolute = 0.012 + (M+N)*pitch → on grid
set x_offset 42.288
set y_offset 42.288
# Pitch = tile dimension + 2 * halo (halo on each side)
set x_pitch [expr {$tile_w + 10.0}]  ;# 5 µm halo per side = 10 µm gap
set y_pitch [expr {$tile_h + 4.320}]  ;# 2.16 µm halo per side

puts "Pitch: ${x_pitch} x ${y_pitch} µm"

# Collect and sort macro instances
set macros {}
foreach inst [$block getInsts] {
    if {[[$inst getMaster] isBlock]} {
        lappend macros $inst
    }
}

puts "Placing [llength $macros] macros in 8×8 grid"

set idx 0
for {set row 0} {$row < 8} {incr row} {
    for {set col 0} {$col < 8} {incr col} {
        if {$idx >= [llength $macros]} break
        set inst [lindex $macros $idx]
        set x [expr {$x_offset + $col * $x_pitch}]
        set y [expr {$y_offset + $row * $y_pitch}]
        $inst setOrigin [ord::microns_to_dbu $x] [ord::microns_to_dbu $y]
        $inst setPlacementStatus "FIRM"
        puts "  [$inst getName] at ($x, $y)"
        incr idx
    }
}

puts "Placed $idx macros"
