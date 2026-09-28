# A place substep of a deployed _deps tree through pathology.tcl:
#   bazelisk run <stage>_deps -- run RUN_SCRIPT=$PWD/probe_deps.tcl \
#     PROBE_ODB=3_4_place_resized.odb OUTPUT_JSON=... PATHOLOGY_TCL=... KEPT_EXPECTED=...
source $::env(SCRIPTS_DIR)/load.tcl
load_design $::env(PROBE_ODB) 2_floorplan.sdc
source $::env(PATHOLOGY_TCL)
estimate_parasitics -placement
pathology_record $::env(OUTPUT_JSON) $::env(KEPT_EXPECTED)
