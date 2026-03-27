# Generate gallery screenshot from a routed design.
#
# Used via orfs_run to produce a single high-quality image
# suitable for the README gallery.
#
# Expects env vars:
#   ODB_FILE      - path to the ODB database to load
#   GALLERY_IMAGE - output image path

# Load the design
read_db $::env(ODB_FILE)

set block [ord::get_db_block]
set bbox [$block getBBox]
set xlo [ord::dbu_to_microns [$bbox xMin]]
set ylo [ord::dbu_to_microns [$bbox yMin]]
set xhi [ord::dbu_to_microns [$bbox xMax]]
set yhi [ord::dbu_to_microns [$bbox yMax]]

# Target 2000px on the longest side
set width_um [expr {$xhi - $xlo}]
set height_um [expr {$yhi - $ylo}]
if {$width_um > $height_um} {
    set width_px 2000
} else {
    set width_px [expr {int(2000.0 * $width_um / $height_um)}]
}

gui::clear_highlights -1
gui::clear_selections

# Start from default visibility (don't clear everything)
# The default renders instances with their type coloring and
# shows routing layers — closest to what the GUI displays.
gui::set_display_controls "Nets/Power" visible false
gui::set_display_controls "Nets/Ground" visible false
gui::set_display_controls "Misc/Scale bar" visible true

# Use -area to crop to die bbox, -width for pixel width
save_image -area [list $xlo $ylo $xhi $yhi] -width $width_px $::env(GALLERY_IMAGE)
