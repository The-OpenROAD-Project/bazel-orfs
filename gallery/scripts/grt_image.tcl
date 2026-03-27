# GRT gallery screenshot — global routing with congestion visible.

read_db $::env(ODB_FILE)

set block [ord::get_db_block]
set bbox [$block getBBox]
set xlo [ord::dbu_to_microns [$bbox xMin]]
set ylo [ord::dbu_to_microns [$bbox yMin]]
set xhi [ord::dbu_to_microns [$bbox xMax]]
set yhi [ord::dbu_to_microns [$bbox yMax]]

set width_um [expr {$xhi - $xlo}]
set height_um [expr {$yhi - $ylo}]
set width_px [expr {$width_um > $height_um ? 2000 : int(2000.0 * $width_um / $height_um)}]

gui::clear_highlights -1
gui::clear_selections

gui::set_display_controls "Nets/Power" visible false
gui::set_display_controls "Nets/Ground" visible false
gui::set_display_controls "Misc/Scale bar" visible true
# Show routing guides
gui::set_display_controls "Route Guides" visible true

gui::fit
save_image -area [list $xlo $ylo $xhi $yhi] -width $width_px $::env(GALLERY_IMAGE)
