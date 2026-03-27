# Top-level MeshWithDelays IO constraints.
#
# Pin placement matches the intended SoC context:
#   Left:   a-matrix inputs (from scratchpad row banks)
#   Top:    b/d-matrix inputs, control request (from scratchpad/controller)
#   Bottom: response outputs (to accumulator/controller)
#   Right:  (unused — no signals naturally exit right in the SoC)

proc match_pins { pattern } {
    set pins {}
    foreach pin [get_ports $pattern] {
        lappend pins [get_name $pin]
    }
    return [lsort $pins]
}

# Left: a-matrix data from scratchpad
set_io_pin_constraint -region left:* -pin_names [concat \
    {*}[match_pins io_a_*]]

# Top: b/d data + control request + clock
set_io_pin_constraint -region top:* -pin_names [concat \
    {*}[match_pins io_b_*] \
    {*}[match_pins io_d_*] \
    {*}[match_pins io_req_*] \
    clock]

# Bottom: response outputs to accumulator/controller
set_io_pin_constraint -region bottom:* -pin_names [concat \
    {*}[match_pins io_resp_*] \
    {*}[match_pins io_tags_in_progress_*]]
