# HPerfMonitor_3: MemBlock's performance monitor.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = HPerfMonitor_3
export DESIGN_NICKNAME         = xiangshan_HPerfMonitor_3
include ../block.mk

# Nothing worth keeping inside: synthesised flat.
export SYNTH_HIERARCHICAL      = 0
