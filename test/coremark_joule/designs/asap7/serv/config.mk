export PLATFORM                = asap7

export DESIGN_NAME             = cmj_serv
export DESIGN_NICKNAME         = serv

export VERILOG_FILES           = @serv//:rtl //test/coremark_joule/rtl:cmj_serv.v \
                                 //test/coremark_joule/flow:cmj_progmem_macros.v \
                                 //test/coremark_joule/rtl:cmj_dmem.v
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

# The two tightly-coupled memories the tile hardens.
#
# Hardened by ORFS's AUTO_MEMORIES path, which calls FakeRAM2.0 -- the
# same generator that produced the platform's own fakeram7_* views, and
# therefore the same generator VeeR's ICCM, DCCM and cache arrays
# already use. That is the point: the memory is 58-85 % of every point's
# power in this study, so a cross-core energy comparison cannot afford
# to have it come from two different models.
#
# The scanner cannot find these memories, and that is deliberate.
# rtl/cmj_progmem.sv is the simulation view and is not in VERILOG_FILES
# above, so the modules reach synthesis undefined and there is no
# inferred $mem to detect. ADDITIONAL_MEMORIES carries the geometry
# instead -- the mechanism variables.yaml documents as "or to describe
# one the scanner cannot find", and the same one asap7/tinyRocket uses
# for its tag and data arrays.
export ADDITIONAL_MEMORIES     = //test/coremark_joule/flow:cmj_progmem.memories

# Two macros in a design whose standard-cell half is small. Taken from
# the veer config, which is the design in this study that already had
# macros in it.
export PLACE_DENSITY_LB_ADDON  = 0.20
export MACRO_PLACE_HALO        = 2 2

# 50, not the 40 the cacheless cores used before section 5.1. The
# memories are most of the design area now, so utilization decides
# almost nothing about the standard cells and everything about how much
# empty die the clock tree has to cross.
#
# Macro placement is RTL-MP's. An earlier revision placed the two macros
# by hand because RTL-MP could not partition two of them against a
# standard-cell half this small (MPL-0045); with the data memory split
# into four byte lanes there are five, and the placer converges on its
# own. What that gives up is a placement identical across the three
# cores, so the memory's wirelength -- and the switching power in it --
# is no longer a controlled constant between them.
export CORE_UTILIZATION        = 50
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
