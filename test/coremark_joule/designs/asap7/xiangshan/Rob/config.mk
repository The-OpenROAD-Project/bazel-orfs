# Rob: reorder buffer: 352 entries with the rename and vtype buffers.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = Rob
export DESIGN_NICKNAME         = xiangshan_Rob
include ../block.mk

export SYNTH_KEEP_MODULES      = RenameBuffer \
                                 VTypeBuffer
