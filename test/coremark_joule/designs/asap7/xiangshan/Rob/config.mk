# Rob: reorder buffer: 352 entries with the rename and vtype buffers.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = Rob
export DESIGN_NICKNAME         = xiangshan_Rob
include ../block.mk

# RobEntryCell is XiangShan patch 0003: the per-entry logic as one
# module, instanced 352 times and synthesised once.
export SYNTH_KEEP_MODULES      = RenameBuffer \
                                 VTypeBuffer \
                                 RobEntryCell
