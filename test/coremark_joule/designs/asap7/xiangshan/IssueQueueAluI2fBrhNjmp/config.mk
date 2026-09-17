# IssueQueueAluI2fBrhNjmp: issue queue.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueAluI2fBrhNjmp
export DESIGN_NICKNAME         = xiangshan_IssueQueueAluI2fBrhNjmp
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesAluI2fBrhNjmp
