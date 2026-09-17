# LsqWrapper: load and store queues.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog).
export DESIGN_NAME             = LsqWrapper
export DESIGN_NICKNAME         = xiangshan_LsqWrapper
include ../block.mk

export SYNTH_KEEP_MODULES      = LoadQueueReplay \
                                 LoadQueueRAW \
                                 LoadQueueRAR \
                                 VirtualLoadQueue \
                                 LoadQueueUncache \
                                 StoreQueue \
                                 PhysicalStoreQueue \
                                 VirtualStoreQueue \
                                 AgeDetector_40
