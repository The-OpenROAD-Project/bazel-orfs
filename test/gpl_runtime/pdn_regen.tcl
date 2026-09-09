# Regenerate the power grid on a finished floorplan: rip up what pdngen
# built, re-source the platform's PDN configuration, run pdngen again.
# The floorplan ODB already carries the grid, so this is the 2_4 step in
# isolation, repeatable from a deployed place tree without redoing the
# 30-minute macro placement in front of it.
#
#   OPENROAD_EXE=/path/to/openroad ./make run \
#     RUN_SCRIPT=/abs/path/pdn_regen.tcl RUN_LOG_NAME_STEM=pdn_regen

source $::env(SCRIPTS_DIR)/load.tcl
erase_non_stage_variables floorplan
load_design 2_floorplan.odb 2_floorplan.sdc

log_cmd pdngen -ripup
source $::env(PDN_TCL)
log_cmd pdngen

report_design_area
orfs_write_db $::env(RESULTS_DIR)/2_4_floorplan_pdn_regen.odb
