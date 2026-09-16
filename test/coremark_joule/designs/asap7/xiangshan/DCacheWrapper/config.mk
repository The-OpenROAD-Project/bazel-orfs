# DCacheWrapper: L1 data cache with its banks and metadata arrays.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = DCacheWrapper
export DESIGN_NICKNAME         = xiangshan_DCacheWrapper
include ../block.mk

export SYNTH_KEEP_MODULES      = MissQueue \
                                 BankedDataArray \
                                 L1ErrorMetaArray \
                                 L1PrefetchSourceArray \
                                 L1CohMetaArray \
                                 L1FlagMetaArray \
                                 MainPipe \
                                 L1RefillLatencyArray
