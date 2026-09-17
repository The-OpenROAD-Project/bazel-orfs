# IntRegFile: integer register file, 224 x 64, 12 read and 9 write ports. Lives in the int Region, flat in the parent.
#
# A register file as a block, because as flops in a sea of cells it is
# what no legaliser spreads: the parent's detailed placement, like the
# fp region's before it, fell to a few thousand overlapping cells per
# hour with the register files' flops and read-mux buffers as the
# residue. Alone, it is small enough to legalise in minutes, and it is
# given room: low utilisation, low density, two sites of padding in
# global placement and a wide legaliser window. This is the macro
# answer available today; the honest one is a generated, bit-sliced
# register file, a later tool.
export DESIGN_NAME             = IntRegFile
export DESIGN_NICKNAME         = xiangshan_IntRegFile
include ../block.mk

export SYNTH_HIERARCHICAL      = 0
export CORE_UTILIZATION        = 20
export PLACE_DENSITY           = 0.35
export CELL_PAD_IN_SITES_GLOBAL_PLACEMENT = 2
export DETAIL_PLACEMENT_ARGS   = -max_displacement "2000 500"
