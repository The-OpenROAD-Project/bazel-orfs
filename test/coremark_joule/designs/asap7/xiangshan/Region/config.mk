# Region: integer region: issue queues, integer execution units and data path.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = Region
export DESIGN_NICKNAME         = xiangshan_Region
include ../block.mk

export SYNTH_KEEP_MODULES      = IssueQueueLdu \
                                 IssueQueueAluMul \
                                 ExuBlock \
                                 DataPath \
                                 IssueQueueAluI2fBrhNjmp \
                                 IssueQueueAluBkuVset \
                                 IssueQueueAluCsrFenceLinkBrhNjmp \
                                 IssueQueueAluDivBrhNjmp \
                                 IssueQueueStdMoud \
                                 IssueQueueStdMoud_1 \
                                 IssueQueueStaMou \
                                 IssueQueueStaMou_1 \
                                 ExeUnitImp \
                                 NewCSR

# The generated register files inside this block (parent config.mk
# says how): the RTL module stays as the simulation model.
export STRUCTURED_MEMORIES     = $(DESIGN_HOME)/asap7/xiangshan/IntRegFile.regfile
