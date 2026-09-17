# VecRegionModule: vector region: issue queues, vector register file and execution units.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = VecRegionModule
export DESIGN_NICKNAME         = xiangshan_VecRegionModule
include ../block.mk

# The issue pipes' partitions ran 9 to 27 minutes each: one execution
# unit (VFEX0..3) holds a divider, an FMA and a converter of 20-30 k
# lines apiece. Kept, each is a partition of its own, and VFMacWrapper's
# four instances are synthesised once; so are VectorCvt's two, which
# were 20 minutes as one VCVTWrapper partition.
export SYNTH_KEEP_MODULES      = IssuePipeVialuVfmaVfdivVidiv \
                                 IssuePipeVialuVimacVmoveVfcvtVfma \
                                 IssuePipeVialuVfma \
                                 IssuePipeVialuVfma_1 \
                                 VIDiv \
                                 VFDivWrapper \
                                 VFMacWrapper \
                                 VCVTWrapper \
                                 VectorCvt \
                                 VIMacU \
                                 IssueQueueVialuVimacVmoveVfcvtVfma \
                                 IssueQueueVialuVfmaVfdivVidiv \
                                 IssueQueueVialuVfma \
                                 IssueQueueVialuVfma_1 \
                                 IssueQueueVstd \
                                 VectorFMAS2

# The vector register file, 128 x 128 with 14 read and 7 write ports: 20
# minutes of yosys on its own and 16 kbit of flops with 14 read muxes for
# the block's placer. Generated instead, as the parent's register files
# are (parent config.mk); the RTL module stays as the simulation model.
export STRUCTURED_MEMORIES     = $(DESIGN_HOME)/asap7/xiangshan/VfRegFile.regfile
