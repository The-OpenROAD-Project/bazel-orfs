export PLATFORM                = asap7

export DESIGN_NAME             = tiny
export DESIGN_NICKNAME         = tiny

# A "//" label, deliberately. Resolving it needs the root of the
# repository this designs tree lives in, which is this tree's own
# package with its depth stripped off -- three components here, two for
# ORFS's flow/designs. A hardcoded two made this file's sources look
# absent and the whole tree was dropped without a message.
export VERILOG_FILES           = //test/designs_fixture/src:tiny.v
export SDC_FILE                = $(DESIGN_HOME)/asap7/tiny/constraints.sdc

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
export SKIP_REPORT_METRICS     = 1
