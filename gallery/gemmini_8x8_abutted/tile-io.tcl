# Tile IO constraints for routing by abutment.
# Pin edges follow systolic data flow: a left→right, b/d top→bottom.
#
# Following mock-array pattern: set region constraint on ONE direction
# only, then mirrored_pins places the opposite side automatically.

proc bus_pins {prefix width} {
    set pins {}
    for {set i 0} {$i < $width} {incr i} {
        lappend pins "${prefix}\[${i}\]"
    }
    return $pins
}

# Right edge: a-outputs + non-symmetric pins (clock, io_bad_dataflow)
# Non-symmetric pins on bottom/top edges get placed on M5 (vertical) at
# the die boundary where DRT can't create access points. Right edge avoids this.
set right_pins [concat [bus_pins io_out_a_0 8] io_bad_dataflow clock]
set_io_pin_constraint -region right:* -pin_names $right_pins

# Mirror left↔right: left pins placed automatically by mirroring
set lr_mirrored {}
for {set i 0} {$i < 8} {incr i} {
    lappend lr_mirrored "io_out_a_0\[${i}\]" "io_in_a_0\[${i}\]"
}
set_io_pin_constraint -mirrored_pins $lr_mirrored

# Bottom edge: all vertical outputs + non-symmetric (region on bottom only)
set bottom_pins [concat \
    [bus_pins io_out_b_0 32] \
    [bus_pins io_out_c_0 32] \
    io_out_control_0_dataflow io_out_control_0_propagate \
    [bus_pins io_out_control_0_shift 5] \
    [bus_pins io_out_id_0 4] \
    io_out_last_0 io_out_valid_0 \
    ]
set_io_pin_constraint -region bottom:* -pin_names $bottom_pins

# Mirror top↔bottom: top pins placed automatically by mirroring
set tb_mirrored {}
for {set i 0} {$i < 32} {incr i} {
    lappend tb_mirrored "io_out_b_0\[${i}\]" "io_in_b_0\[${i}\]"
}
for {set i 0} {$i < 32} {incr i} {
    lappend tb_mirrored "io_out_c_0\[${i}\]" "io_in_d_0\[${i}\]"
}
lappend tb_mirrored \
    io_out_control_0_dataflow io_in_control_0_dataflow \
    io_out_control_0_propagate io_in_control_0_propagate
for {set i 0} {$i < 5} {incr i} {
    lappend tb_mirrored "io_out_control_0_shift\[${i}\]" "io_in_control_0_shift\[${i}\]"
}
for {set i 0} {$i < 4} {incr i} {
    lappend tb_mirrored "io_out_id_0\[${i}\]" "io_in_id_0\[${i}\]"
}
lappend tb_mirrored \
    io_out_last_0 io_in_last_0 \
    io_out_valid_0 io_in_valid_0
set_io_pin_constraint -mirrored_pins $tb_mirrored
