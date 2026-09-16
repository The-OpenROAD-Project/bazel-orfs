# The same design with the wires taken out.
#
# This is the study's upper bound, and it is the cheapest number in it.
#
# Every question here -- whether a throwaway global route would let the
# early repair decide better, whether the single `set_wire_rc` constant
# mis-prices the layers routing actually uses -- is a question about the
# *wire* part of a path delay. So whatever fraction of the achieved
# period is wire delay is a hard ceiling on the whole hypothesis: a
# parasitics model cannot be wrong by more than the thing it models.
# Measure that fraction first and a design that cannot possibly show the
# effect is identified for the price of one STA run, instead of a
# campaign that reports a well-formed zero.
#
# ORFS's load.tcl sources LAYER_PARASITICS_FILE *in place of* the
# platform's setRC.tcl, so installing this file is all it takes -- the
# stage ODB, the netlist and the placement are untouched, and the only
# difference from the control run is that no wire has resistance or
# capacitance.
#
# Not exactly zero: `estimate_parasitics` checks that the corner has wire
# caps at all, and a literal 0 risks a divide or a "no wire cap" error
# rather than a clean answer. 1e-9 against asap7's 1.66e-1 is five orders
# of magnitude down -- wire delay is gone to any precision this study can
# read -- while every command still takes the same path through the tool.

# Signal wires only. The clock tree keeps the platform's real RC, which
# matters: zeroing it too would also remove insertion delay and skew, and
# the difference from the control run would then be "all wire effects
# everywhere" rather than the data-path wire delay that setup repair
# actually works on. The platform table is installed first so every layer
# and via keeps its real value and only the signal constant is replaced.
source $::env(PLATFORM_DIR)/setRC.tcl

set zero_r 1e-9
set zero_c 1e-9
set_wire_rc -signal -resistance $zero_r -capacitance $zero_c

puts "ZERO_RC installed: signal wire R=$zero_r C=$zero_c, clock RC left real"
