# IssueQueueAluCsrFenceLinkBrhNjmp: issue queue.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueAluCsrFenceLinkBrhNjmp
export DESIGN_NICKNAME         = xiangshan_IssueQueueAluCsrFenceLinkBrhNjmp
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesAluCsrFenceLinkBrhNjmp
