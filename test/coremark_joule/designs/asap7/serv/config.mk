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
export AUTO_MEMORIES           = 1

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
