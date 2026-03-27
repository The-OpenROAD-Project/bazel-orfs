# Tile ppl run for OpenROAD#9902

AcKoucher asked for the Tile ppl run to investigate why die-edge pins
end up off the M5 track grid in the hierarchical gemmini_8x8_abutted flow.

Plan: use `substeps = True` on the Tile macro to get a `place_iop` substep
target, build it, create an untar-and-run archive with `io_placement_issue`,
verify, and attach to the issue.

Need to sync to latest openroad-demo main first.
