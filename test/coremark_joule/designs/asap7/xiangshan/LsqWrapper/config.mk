# LsqWrapper: load and store queues.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it (the parent's kept modules
# that fall in this subtree, read off the generated Verilog). ForwardModule
# is the store queue's forwarding CAM, a third of a 45-minute partition.
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
                                 ForwardModule \
                                 SqEntryCell \
                                 VirtualStoreQueue \
                                 AgeDetector_40
