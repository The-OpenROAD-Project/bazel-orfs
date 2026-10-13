# The arm's minimum period at this stage: clock period minus worst slack,
# with placement parasitics; and its instance count and area.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
estimate_parasitics -placement
set p [find_timing_paths -path_delay max -group_path_count 1]
set slack [get_property [lindex $p 0] slack]
set f [open [file join $::env(WORK_HOME) $::env(OUTPUT)] w]
puts $f [format "{\"period_ps\": %.1f, \"instances\": %d, \"area_um2\": %.1f}" \
  [expr { 200.0 - $slack }] [llength [get_cells *]] \
  [expr { [rsz::design_area] * 1e12 }]]
close $f
