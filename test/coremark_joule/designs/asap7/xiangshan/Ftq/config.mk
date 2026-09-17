# Ftq: fetch target queue, with its four generated register files.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = Ftq
export DESIGN_NICKNAME         = xiangshan_Ftq
include ../block.mk

export SYNTH_KEEP_MODULES      = ResolveQueue

# The four generated register files (XiangShan patch 0002, parent
# config.mk says how); the RTL modules are the simulation models.
export STRUCTURED_MEMORIES     = $(DESIGN_HOME)/asap7/xiangshan/FtqEntryQueue.regfile \
                                 $(DESIGN_HOME)/asap7/xiangshan/FtqMetaQueueRedirect.regfile \
                                 $(DESIGN_HOME)/asap7/xiangshan/FtqMetaQueueResolve.regfile \
                                 $(DESIGN_HOME)/asap7/xiangshan/FtqMetaQueueCommit.regfile
