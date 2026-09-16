# ICache: instruction cache, small enough to synthesise flat.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = ICache
export DESIGN_NICKNAME         = xiangshan_ICache
include ../block.mk

export SYNTH_HIERARCHICAL      = 0
