# After CTS, with the tree built: a setup repair that only swaps cells to
# a faster Vt class. Every other repair move stays off, as the flow has it
# (SKIP_CTS_REPAIR_TIMING); this is the one pass that lets the LVT and
# SLVT cells ASAP7_USE_VT brings in reach the critical paths. The blocks
# are abstracted at cts, so this is the last point at which a block can
# swap. A swap keeps the footprint, so the placement stays legal; checked.
repair_timing_helper -setup -sequence vt_swap
check_placement -verbose
