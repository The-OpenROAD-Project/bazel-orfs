# ExuBlock: integer execution units (ALU, MUL, DIV, BKU, CSR, jumps and branches).
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = ExuBlock
export DESIGN_NICKNAME         = xiangshan_ExuBlock
include ../block.mk

export SYNTH_KEEP_MODULES      = ExeUnitImp \
                                 NewCSR
