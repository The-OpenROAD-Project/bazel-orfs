# VecRegionModule: vector region: issue queues, vector register file and execution units.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = VecRegionModule
export DESIGN_NICKNAME         = xiangshan_VecRegionModule
include ../block.mk

export SYNTH_KEEP_MODULES      = IssuePipeVialuVfmaVfdivVidiv \
                                 IssuePipeVialuVimacVmoveVfcvtVfma \
                                 IssuePipeVialuVfma \
                                 IssuePipeVialuVfma_1 \
                                 IssueQueueVialuVimacVmoveVfcvtVfma \
                                 IssueQueueVialuVfmaVfdivVidiv \
                                 IssueQueueVialuVfma \
                                 IssueQueueVialuVfma_1 \
                                 IssueQueueVstd \
                                 VfRegFile \
                                 VectorFMAS2
