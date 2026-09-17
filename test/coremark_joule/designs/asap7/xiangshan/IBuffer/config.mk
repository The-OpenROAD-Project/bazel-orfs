# IBuffer: instruction buffer.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = IBuffer
export DESIGN_NICKNAME         = xiangshan_IBuffer
include ../block.mk

# Nothing worth keeping inside: synthesised flat.
export SYNTH_HIERARCHICAL      = 0
