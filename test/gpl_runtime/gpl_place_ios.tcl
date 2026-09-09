# The future place stage as one OpenROAD run: cells and IO pins in the same
# Nesterov solve (global_placement -place_ios) straight from the floorplan
# ODB, then place_pins to legalize the pins onto tracks. Replaces ORFS's
# 3_1_place_gp_skip_io / 3_2_place_iop / 3_3_place_gp triple.
#
# -place_ios cannot be combined with -timing_driven or -routability_driven
# (GPL-0179 / GPL-0181), so this is the placer core: what the study
# profiles. The arguments otherwise follow global_place.tcl.
#
# Run inside a deployed place tree, with any OpenROAD binary:
#
#   OPENROAD_EXE=/path/to/openroad ./make run \
#     RUN_SCRIPT=/abs/path/gpl_place_ios.tcl RUN_LOG_NAME_STEM=3_1_place_gp_ios

utl::set_metrics_stage "globalplace__{}"
source $::env(SCRIPTS_DIR)/load.tcl
erase_non_stage_variables place
load_design 2_floorplan.odb 2_floorplan.sdc

set_dont_use $::env(DONT_USE_CELLS)

if { ![env_var_exists_and_non_empty FOOTPRINT] } {
  if { !$::env(DONT_BUFFER_PORTS) } {
    puts "Perform port buffering..."
    buffer_ports {*}[env_var_or_empty BUFFER_PORTS_ARGS]
  }
}

set global_placement_args {}
append_env_var global_placement_args GPL_RANDOM_SEED -random_seed 1
lappend global_placement_args -force_center_initial_place
lappend global_placement_args -min_phi_coef $::env(MIN_PLACE_STEP_COEF)
lappend global_placement_args -max_phi_coef $::env(MAX_PLACE_STEP_COEF)

log_cmd global_placement -place_ios \
  -density [place_density_with_lb_addon] \
  -pad_left $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) \
  -pad_right $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) \
  {*}$global_placement_args \
  {*}[env_var_or_empty GLOBAL_PLACEMENT_ARGS]

log_cmd place_pins \
  -hor_layers $::env(IO_PLACER_H) \
  -ver_layers $::env(IO_PLACER_V) \
  {*}[env_var_or_empty PLACE_PINS_ARGS]

report_design_area

orfs_write_db $::env(RESULTS_DIR)/3_1_place_gp_ios.odb
