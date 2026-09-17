# MemCtrl: memory dependence prediction: SSIT and LFST.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = MemCtrl
export DESIGN_NICKNAME         = xiangshan_MemCtrl
include ../block.mk

export SYNTH_KEEP_MODULES      = SSIT \
                                 LFST
