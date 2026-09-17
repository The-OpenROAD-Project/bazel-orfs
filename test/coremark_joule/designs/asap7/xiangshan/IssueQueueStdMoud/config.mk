# IssueQueueStdMoud: issue queue.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IssueQueueStdMoud
export DESIGN_NICKNAME         = xiangshan_IssueQueueStdMoud
include ../block.mk

export SYNTH_KEEP_MODULES      = EntriesStdMoud
