# Generate floorplan screenshot showing macro placement, pins, and PDN.
#
# Optimized for hierarchical designs with macro arrays — shows the
# macro grid, pin locations, power distribution, and routing blockages
# without overwhelming layer detail.
#
# Expects env vars:
#   ODB_FILE      - path to the ODB database to load
#   GALLERY_IMAGE - output image path

read_db $::env(ODB_FILE)

set block [ord::get_db_block]
set bbox [$block getBBox]
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

# Start clean
gui::set_display_controls "*" visible false

# Macro instances
gui::set_display_controls "Instances/*" visible true
gui::set_display_controls "Instances/Physical/Fill cell" visible false

# Metal layers — shows PDN straps and pin shapes
gui::set_display_controls "Layers/*" visible true

# Power/ground — shows PDN grid between macros
gui::set_display_controls "Nets/Power" visible true
gui::set_display_controls "Nets/Ground" visible true

# Scale bar
gui::set_display_controls "Misc/Scale bar" visible true

gui::fit
puts "Generating floorplan image..."
save_image -area [list $xlo $ylo $xhi $yhi] -width $width_px $::env(GALLERY_IMAGE)
