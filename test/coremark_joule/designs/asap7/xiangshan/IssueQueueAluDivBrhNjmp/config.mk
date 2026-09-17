# IssueQueueAluDivBrhNjmp: issue queue.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueAluDivBrhNjmp
export DESIGN_NICKNAME         = xiangshan_IssueQueueAluDivBrhNjmp
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesAluDivBrhNjmp
