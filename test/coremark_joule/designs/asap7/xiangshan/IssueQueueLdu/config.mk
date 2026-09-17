# IssueQueueLdu: issue queue, 3 instances in the parent.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueLdu
export DESIGN_NICKNAME         = xiangshan_IssueQueueLdu
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesLdu
