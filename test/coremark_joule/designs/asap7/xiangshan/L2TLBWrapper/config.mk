# L2TLBWrapper: L2 TLB and page-table walker.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = L2TLBWrapper
export DESIGN_NICKNAME         = xiangshan_L2TLBWrapper
include ../block.mk

export SYNTH_KEEP_MODULES      = PtwCache \
                                 LLPTW \
                                 PMP \
                                 PMPChecker \
                                 PTW \
                                 HPTW
