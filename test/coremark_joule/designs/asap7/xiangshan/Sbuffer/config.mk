# Sbuffer: store buffer.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = Sbuffer
export DESIGN_NICKNAME         = xiangshan_Sbuffer
include ../block.mk

export SYNTH_KEEP_MODULES      = SbufferData
