# Dispatch: dispatch and the busy tables.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = Dispatch
export DESIGN_NICKNAME         = xiangshan_Dispatch
include ../block.mk

export SYNTH_KEEP_MODULES      = BusyTable \
                                 BusyTable_1

# 12,969 pins on 309 k cells: at the shared 40 % utilisation the die's
# perimeter holds 12,384 pin positions (PPL-0024, "increase the die
# perimeter from 1194.92 um to 1245.02 um"). A quarter utilisation gives
# a 26 % longer side and room for the pins; the block is pin-bound, not
# cell-bound.
export CORE_UTILIZATION        = 25
