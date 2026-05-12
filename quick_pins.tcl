# quick_pins: a cheap pin-placement shortcut for exploration flows.
#
# The default ORFS pin-placement path is:
#
#   global_place_skip_io.tcl    runs `global_placement -skip_io` to give
#                               place_pins better wirelength info. On a
#                               large multi-million-cell design this step
#                               can take tens of minutes.
#   io_placement.tcl            runs `place_pins` (fast).
#
# For RTL exploration we will re-run real placement anyway, and the pin
# positions only need to be plausible — not optimal. The slow GP-skip-io
# is the wrong place to spend exploration wall time.
#
# OpenROAD's ppl module handles unplaced cells by treating their position
# as the die centre for wirelength computation — see the PPL README:
#   "For designs with unplaced cells, the net wirelength is computed
#    considering the center of the die area as the unplaced cells position."
#
# So we just run `place_pins` directly, before global_place_skip_io. After
# this hook fires, `[all_pins_placed]` is true and global_place_skip_io
# exits early. (See global_place_skip_io.tcl for the early-exit gate.) A
# companion FOOTPRINT_TCL stub is set so io_placement.tcl skips its own
# place_pins call.
log_cmd place_pins \
    -hor_layers $::env(IO_PLACER_H) \
    -ver_layers $::env(IO_PLACER_V) \
    {*}[env_var_or_empty PLACE_PINS_ARGS]
puts "quick_pins: placed pins via place_pins (cells at die center) — global_place -skip_io will be bypassed"
