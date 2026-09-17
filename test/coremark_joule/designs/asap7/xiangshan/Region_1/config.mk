# Region_1: floating-point region: issue queues, fp execution units and data path.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog), plus the
# fp execution units under ExuBlock_1, a 35-minute partition as one.
export DESIGN_NAME             = Region_1
export DESIGN_NICKNAME         = xiangshan_Region_1
include ../block.mk

export SYNTH_KEEP_MODULES      = IssueQueueFaluFmacFdiv \
                                 ExuBlock_1 \
                                 ExeUnitImp_10 \
                                 ExeUnitImp_9 \
                                 DataPath_1 \
                                 IssueQueueFaluFmacFcvtFcmp \
                                 IssueQueueFaluFmac

# The generated register files inside this block (parent config.mk
# says how): the RTL module stays as the simulation model.
export STRUCTURED_MEMORIES     = $(DESIGN_HOME)/asap7/xiangshan/FpRegFilePart0.regfile \
                                 $(DESIGN_HOME)/asap7/xiangshan/FpRegFilePart1.regfile \
                                 $(DESIGN_HOME)/asap7/xiangshan/FpRegFilePart2.regfile \
                                 $(DESIGN_HOME)/asap7/xiangshan/FpRegFilePart3.regfile
