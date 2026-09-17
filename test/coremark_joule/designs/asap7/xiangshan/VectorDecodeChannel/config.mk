# VectorDecodeChannel: one vector decode channel, 105 k lines of
# combinational decode; the decode stage instantiates it eight times, so
# the parent places eight copies of one placed block instead of the
# 942 k line DecodeStage. Everything shared is in ../block.mk.
export DESIGN_NAME             = VectorDecodeChannel
export DESIGN_NICKNAME         = xiangshan_VectorDecodeChannel
include ../block.mk

# No children worth keeping: synthesised flat.
export SYNTH_HIERARCHICAL      = 0
