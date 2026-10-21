# The keep census of an arm, on its floorplan: what synthesis made of the
# arm's keep list, before any wire. Run by the arm tree's make:
#
#   make run RUN_SCRIPT=census_floorplan.tcl CENSUS_TCL=... CENSUS_OUT=...
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc
source $::env(CENSUS_TCL)
keep_census
