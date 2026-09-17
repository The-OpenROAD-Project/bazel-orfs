# DCacheWrapper: L1 data cache with its banks and metadata arrays.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = DCacheWrapper
export DESIGN_NICKNAME         = xiangshan_DCacheWrapper
include ../block.mk

# MissQueue's partition ran 12 minutes; its sixteen MissEntry instances
# are two thirds of it and, kept, are synthesised once.
export SYNTH_KEEP_MODULES      = MissQueue \
                                 MissEntry \
                                 BankedDataArray \
                                 L1ErrorMetaArray \
                                 L1PrefetchSourceArray \
                                 L1CohMetaArray \
                                 L1FlagMetaArray \
                                 MainPipe \
                                 L1RefillLatencyArray
