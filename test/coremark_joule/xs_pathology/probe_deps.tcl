# A place substep of a deployed tree through pathology.tcl:
#   bazelisk run //:dirty -- start <flow> place
#   <tree>/make run RUN_SCRIPT=$PWD/probe_deps.tcl \
#     PROBE_ODB=3_4_place_resized.odb OUTPUT_JSON=... PATHOLOGY_TCL=... KEPT_EXPECTED=...
source $::env(SCRIPTS_DIR)/load.tcl
# with the .sdc beside it, the floorplan's constraints copied through
load_design $::env(PROBE_ODB)
source $::env(PATHOLOGY_TCL)
estimate_parasitics -placement
pathology_record $::env(OUTPUT_JSON) $::env(KEPT_EXPECTED)
