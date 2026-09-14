# Write the gate-level netlist for the stage this runs against.
#
# The flow writes an ODB at each stage boundary but not a Verilog
# netlist, and the gate-level simulation that produces the SAIF needs
# one. Taking it from the stage's own ODB is what keeps the simulated
# netlist and the netlist power is reported on the same netlist -- the
# alignment that makes a SAIF bind at all. A SAIF captured against one
# stage and applied to another leaves nets unmatched, and OpenSTA
# silently falls back to default activity for them.
#
# load.tcl, not open.tcl: open.tcl is the interactive/GUI entry point and
# pulls in more than reading an ODB and writing a netlist needs. It only
# defines load_design, so the stage's files are named here -- as a
# parameter, so this serves any stage rather than just global route.
source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

write_verilog $::env(OUTPUT)
