# DataPath: integer data path: the register cache and the generated IntRegFile.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = DataPath
export DESIGN_NICKNAME         = xiangshan_DataPath
include ../block.mk

# Nothing worth keeping inside: synthesised flat.
export SYNTH_HIERARCHICAL      = 0

# The generated integer register file (parent config.mk says how);
# the RTL module stays as the simulation model.
export STRUCTURED_MEMORIES     = $(DESIGN_HOME)/asap7/xiangshan/IntRegFile.regfile
