# Rename: rename: the rename tables, free lists and the compressor.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = Rename
export DESIGN_NICKNAME         = xiangshan_Rename
include ../block.mk

export SYNTH_KEEP_MODULES      = RenameTableWrapper \
                                 CompressUnit
