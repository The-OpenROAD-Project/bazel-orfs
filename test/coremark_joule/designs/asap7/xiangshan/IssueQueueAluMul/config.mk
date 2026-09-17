# IssueQueueAluMul: issue queue, 2 instances in the parent.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueAluMul
export DESIGN_NICKNAME         = xiangshan_IssueQueueAluMul
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesAluMul
