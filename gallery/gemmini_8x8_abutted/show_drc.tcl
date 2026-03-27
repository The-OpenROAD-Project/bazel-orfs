# Show DRC violations on routed design.
#
# Loads the routed ODB, runs DRC check, enables DRC markers,
# and saves an image showing where violations are.
#
# Run via: tmp/.../make run OR_ARGS="-gui" \
#   OPENROAD_CMD="xvfb-run -a $(OPENROAD_EXE) -exit $(OPENROAD_ARGS)" \
#   RUN_SCRIPT=$(pwd)/gemmini_8x8_abutted/show_drc.tcl

source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_2_route.odb 5_1_grt.sdc

# Run DRC check
set_thread_count [exec nproc]
check_drc

set block [ord::get_db_block]
set bbox [$block getDieArea]
set xlo [ord::dbu_to_microns [$bbox xMin]]
set ylo [ord::dbu_to_microns [$bbox yMin]]
set xhi [ord::dbu_to_microns [$bbox xMax]]
set yhi [ord::dbu_to_microns [$bbox yMax]]
set width_px [expr {($xhi-$xlo) > ($yhi-$ylo) ? 2000 : int(2000.0*($xhi-$xlo)/($yhi-$ylo))}]

gui::set_display_controls "*" visible false
gui::set_display_controls "Layers/*" visible true
gui::set_display_controls "Instances/*" visible true
gui::set_display_controls "Instances/Physical/Fill cell" visible false
gui::set_display_controls "Misc/Scale bar" visible true

# Show DRC markers
gui::set_display_controls "DRC Viewer/*" visible true

gui::fit
save_image -area [list $xlo $ylo $xhi $yhi] -width $width_px /tmp/drc_violations.webp
puts "Wrote /tmp/drc_violations.webp"
