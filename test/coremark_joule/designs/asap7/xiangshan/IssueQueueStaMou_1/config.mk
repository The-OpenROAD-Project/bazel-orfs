# IssueQueueStaMou_1: issue queue.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueStaMou_1
export DESIGN_NICKNAME         = xiangshan_IssueQueueStaMou_1
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesStaMou
