# Region_1: floating-point region (Region is the integer one, kept flat).
#
# NOT in BLOCKS (see ../config.mk): kept as the record of what was tried
# before the block was given up on. The two failures are documented at
# the bottom of this file.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = Region_1
export DESIGN_NICKNAME         = xiangshan_Region_1
include ../block.mk

export SYNTH_KEEP_MODULES      = IssueQueueFaluFmacFdiv \
                                 ExuBlock_1 \
                                 DataPath_1 \
                                 IssueQueueFaluFmacFcvtFcmp \
                                 IssueQueueFaluFmac \
                                 FloatFMA

# More room than the other blocks. At the shared 40 % utilisation the
# resizer's growth left detailed placement legalising at 53 % (the five
# others sit at 41-42 %), and the negotiation legalizer was still at
# 600 k violations after three hours; the four FpRegFilePart flop arrays
# with their read muxes are what packs it. Loosened until the block
# legalises in minutes like its siblings.
export CORE_UTILIZATION        = 28
export PLACE_DENSITY           = 0.45

# The looser utilisation was not enough: legalisation still stopped at
# 17 k misaligned cells and 1.5 k overlaps after 1,400 iterations and
# 4 h 10 min, every one of them in fpDataPath -- the register-file flops
# and the buffers on their read muxes. That is local density the
# legaliser cannot spread inside its default +/-500-site window, not an
# average. Two textbook remedies: pad every cell by two sites during
# global placement so the array arrives spread out, and let detailed
# placement move a cell further to find a legal site.
export CELL_PAD_IN_SITES_GLOBAL_PLACEMENT = 2
export DETAIL_PLACEMENT_ARGS   = -max_displacement "2000 500"
