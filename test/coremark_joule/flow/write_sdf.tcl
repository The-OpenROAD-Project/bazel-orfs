# Write the SDF for the stage this runs against.
#
# Glitch power (5.2) is a transition that happens because two inputs
# arrive at different times, so it exists only in a simulation that
# knows how long each path takes. This is where those delays come from:
# the same ODB the netlist and the power report come from, so the
# delays, the netlist and the activity all describe one design.
#
# estimate_parasitics first, for the same reason power_grt.tcl does it:
# at global route the wire delays are predicted from the global routes
# rather than extracted, and without them every net delay would be zero
# and the interconnect half of a glitch would vanish.
#
# -no_timestamp keeps the output byte-stable, so a rebuild that changes
# nothing produces an identical file and the cache holds.
#
# Required env:
#   STAGE_STEM   ORFS stage stem, e.g. 5_1_grt
#   OUTPUT       where to write the .sdf
source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

log_cmd estimate_parasitics -global_routing

write_sdf -no_timestamp -include_typ $::env(OUTPUT)
