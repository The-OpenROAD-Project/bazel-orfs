# DecodeStage: decode: eight decode channels, the uop buffer and its select logic.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = DecodeStage
export DESIGN_NICKNAME         = xiangshan_DecodeStage
include ../block.mk

export SYNTH_KEEP_MODULES      = VectorDecodeChannel \
                                 SimpleDecodeChannel \
                                 UopBufferCtrlDecoder
