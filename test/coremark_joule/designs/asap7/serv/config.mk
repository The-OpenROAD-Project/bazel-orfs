export PLATFORM                = asap7

export DESIGN_NAME             = cmj_serv
export DESIGN_NICKNAME         = serv

export VERILOG_FILES           = @serv//:rtl //test/coremark_joule/rtl:cmj_serv.v
export SDC_FILE                = $(DESIGN_HOME)/asap7/serv/constraints.sdc

# SERV is the core that makes the per-unit breakdown work. Its RTL is
# written as one module per architectural function, so the kept list maps
# almost one-to-one onto the units in units.json and very little falls
# into "other".
export SYNTH_HIERARCHICAL      = 1
export SYNTH_KEEP_MODULES      = serv_decode serv_immdec serv_alu serv_bufreg \
                                 serv_bufreg2 serv_ctrl serv_state serv_mem_if \
                                 serv_csr serv_rf_if serv_rf_ram_if serv_rf_ram

# SERV keeps its register file in an SRAM rather than in flops, which is
# the core's whole architectural trick. Hardened as flops it would
# dominate the area and power of a ~2k-cell core and the measurement
# would be of the wrong thing.
# Run OpenROAD hierarchically, so the module boundaries SYNTH_KEEP_MODULES
# preserved survive into the ODB and the written netlist.
#
# Without it the flow is flat: the ODB carries no module structure and
# write_verilog emits one flattened module, so there is nothing for
# `report_power -saif -instances` to attribute power to. Keeping the
# hierarchy through synthesis and then discarding it in OpenROAD would
# leave the whole functional-unit breakdown with a single unit in it.
export OPENROAD_HIERARCHICAL    = 1

export AUTO_MEMORIES           = 1

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65

# Metrics reporting off. This is the only line of the FAST_SETTINGS dict
# in //test:BUILD that a measurement study can take -- every other entry
# in it changes the netlist, and a study cannot buy speed with the thing
# it measures. §3.6 of the paper has the list and the reasoning.
#
# Nothing here reads ORFS's metrics: power comes from
# flow/power_grt.tcl, the achieved period from flow/period_probe.tcl,
# and auto_floorplan takes WNS from sta::worst_slack_cmd directly.
export SKIP_REPORT_METRICS     = 1
