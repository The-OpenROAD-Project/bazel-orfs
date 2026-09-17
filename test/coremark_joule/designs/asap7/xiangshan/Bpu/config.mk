# Bpu: branch prediction unit: every predictor and its tables.
# Everything shared is in ../block.mk; this file names the block and
# what parallel synthesis keeps inside it.
export DESIGN_NAME             = Bpu
export DESIGN_NICKNAME         = xiangshan_Bpu
include ../block.mk

# The predictors' partitions ran 6 to 10 minutes each. Kept below them:
# Tage's eight tables, the main BTB's four internal banks and their
# write buffer, and the SC's write-buffered table, so a partition is a
# table rather than a predictor. A module instanced more than once
# (MainBtbInternalBank x4, WriteBuffer_68 x2) is synthesised once.
export SYNTH_KEEP_MODULES      = MainBtbAlignBank \
                                 MainBtbInternalBank \
                                 WriteBuffer_4 \
                                 Tage \
                                 TageTable \
                                 TageTable_1 \
                                 TageTable_2 \
                                 TageTable_3 \
                                 TageTable_4 \
                                 TageTable_5 \
                                 TageTable_6 \
                                 TageTable_7 \
                                 Sc \
                                 Sc_Anon_7 \
                                 WriteBuffer_68 \
                                 AheadBtb \
                                 Phr \
                                 MicroTage \
                                 Ittage

# 210 predictor tables: RTL-MP fails at its first TAGE cluster (MPL-0008)
# at this count, as it did on the flat design's 303. The annealer from
# the parent places them; same knobs, same reasons (parent config.mk).
export MACRO_PLACEMENT_TCL     = $(DESIGN_HOME)/asap7/xiangshan/anneal_in_flow.tcl
export ANNEAL_DUMP_TCL         = //test/coremark_joule/flow/macro_anneal:dump_macros.tcl
export ANNEAL_PY               = //test/coremark_joule/flow/macro_anneal:macro_anneal.py
export ANNEAL_SEED             = 1
export ANNEAL_DEPTH            = 3
export ANNEAL_MIN_CLUSTER      = 1
export ANNEAL_CHANNEL_UM       = 4.0
export ANNEAL_BLOCK_GAP_UM     = 10.8
export ANNEAL_FILL             = 0.5
export ANNEAL_STRAP_PITCH_UM   = 5.4
export ANNEAL_STRAP_OFFSET_UM  = 0.3
export ANNEAL_STRAP_PAIR_UM    = 0.312
