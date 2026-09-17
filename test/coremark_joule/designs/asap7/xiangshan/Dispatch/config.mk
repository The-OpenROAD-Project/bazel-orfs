# Dispatch: dispatch and the busy tables.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = Dispatch
export DESIGN_NICKNAME         = xiangshan_Dispatch
include ../block.mk

export SYNTH_KEEP_MODULES      = BusyTable \
                                 BusyTable_1
