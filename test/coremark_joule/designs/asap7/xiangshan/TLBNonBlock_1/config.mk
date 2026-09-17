# TLBNonBlock_1: a load/store data TLB.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = TLBNonBlock_1
export DESIGN_NICKNAME         = xiangshan_TLBNonBlock_1
include ../block.mk

# Nothing worth keeping inside: synthesised flat.
export SYNTH_HIERARCHICAL      = 0
