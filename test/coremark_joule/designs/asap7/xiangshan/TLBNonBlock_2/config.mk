# TLBNonBlock_2: a load/store data TLB.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = TLBNonBlock_2
export DESIGN_NICKNAME         = xiangshan_TLBNonBlock_2
include ../block.mk

# Nothing worth keeping inside: synthesised flat.
export SYNTH_HIERARCHICAL      = 0
