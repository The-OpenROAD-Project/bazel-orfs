# The place stage through pathology.tcl, as an orfs_run: OUTPUT_JSON is
# the record, KEPT_EXPECTED the stated list of kept modules.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
source $::env(PATHOLOGY_TCL)
estimate_parasitics -placement
pathology_record $::env(OUTPUT_JSON) $::env(KEPT_EXPECTED)
