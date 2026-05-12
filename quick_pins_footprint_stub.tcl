# Stub sourced as FOOTPRINT_TCL when quick_pins is enabled.
#
# ORFS's io_placement.tcl reads FOOTPRINT_TCL as a sentinel: if set,
# io_placement just `cp`s the GP-skip-io ODB to the IO-placement ODB
# instead of calling place_pins again.
#
# We've already placed pins via PRE_GLOBAL_PLACE_SKIP_IO_TCL (quick_pins.tcl),
# so this stub's only job is to be the sentinel — no commands needed.
puts "quick_pins_footprint_stub: pins were placed in PRE_GLOBAL_PLACE_SKIP_IO_TCL"
