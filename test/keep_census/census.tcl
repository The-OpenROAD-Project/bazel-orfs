# The keep census on the placed design, every reg2reg path (target 0).
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
estimate_parasitics -placement
source $::env(CENSUS_TCL)
keep_census
