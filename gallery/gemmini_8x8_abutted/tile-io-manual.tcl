# Manual pin placement for Tile macro — used as IO_CONSTRAINTS.
#
# Pins extend from track position to die edge so the parent router
# can access them. write_abstract_lef creates OBS covering the Tile
# interior — pins must poke through to the boundary.
#
# ASAP7 M4/M5 track pitch: 0.048, offset: 0.012
# Die: 25.920 x 25.920 µm

set die_w 25.920
set die_h 25.920

# Track spacing
set sp4 0.192  ;# 4 tracks apart
set sp2 0.096  ;# 2 tracks apart

# Pin track positions (inset from edge, on grid)
set left_x  0.492   ;# 0.012 + 10*0.048
set right_x 25.404  ;# 0.012 + 529*0.048
set top_y   25.404
set bot_y   0.492
set x_start 2.028   ;# 0.012 + 42*0.048

# Pin dimensions: extend to die edge for hierarchical access
# Left:   M5 vertical, X from 0 to left_x + half_width
# Right:  M5 vertical, X from right_x - half_width to die_w
# Top:    M4 horizontal, Y from top_y - half_height to die_h
# Bottom: M4 horizontal, Y from 0 to bot_y + half_height

set m5_w 0.024
set m4_h 0.024

# Left edge pin: extends from X=0 to pin position
set left_pin_w $left_x  ;# ~0.492
# Right edge pin: extends from pin position to X=die_w
set right_pin_w [expr {$die_w - $right_x}]  ;# ~0.516
# Top edge pin: extends from pin position to Y=die_h
set top_pin_h [expr {$die_h - $top_y}]  ;# ~0.516
# Bottom edge pin: extends from Y=0 to pin position
set bot_pin_h $bot_y  ;# ~0.492

# Pin center = midpoint of the extended shape
set left_cx  [expr {$left_pin_w / 2.0}]
set right_cx [expr {$right_x + $right_pin_w / 2.0}]
set top_cy   [expr {$top_y + $top_pin_h / 2.0}]
set bot_cy   [expr {$bot_pin_h / 2.0}]

# LEFT edge: io_in_a_0[0..7] on M5
for {set i 0} {$i < 8} {incr i} {
    set y [expr {4.044 + $i * $sp4}]
    place_pin -pin_name "io_in_a_0\[$i\]" -layer M5 \
        -location "$left_cx $y" -pin_size "$left_pin_w 0.084"
}

# RIGHT edge: io_out_a_0[0..7] + clock + io_bad_dataflow on M5
for {set i 0} {$i < 8} {incr i} {
    set y [expr {4.044 + $i * $sp4}]
    place_pin -pin_name "io_out_a_0\[$i\]" -layer M5 \
        -location "$right_cx $y" -pin_size "$right_pin_w 0.084"
}
place_pin -pin_name clock -layer M5 \
    -location "$right_cx 5.532" -pin_size "$right_pin_w 0.084"
place_pin -pin_name io_bad_dataflow -layer M5 \
    -location "$right_cx 5.724" -pin_size "$right_pin_w 0.084"

# TOP edge: all inputs on M4, extending to die top
set idx 0
for {set i 0} {$i < 32} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_in_b_0\[$i\]" -layer M4 \
        -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
    incr idx
}
for {set i 0} {$i < 32} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_in_d_0\[$i\]" -layer M4 \
        -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
    incr idx
}
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_in_control_0_dataflow -layer M4 \
    -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
incr idx
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_in_control_0_propagate -layer M4 \
    -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
incr idx
for {set i 0} {$i < 5} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_in_control_0_shift\[$i\]" -layer M4 \
        -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
    incr idx
}
for {set i 0} {$i < 4} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_in_id_0\[$i\]" -layer M4 \
        -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
    incr idx
}
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_in_last_0 -layer M4 \
    -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
incr idx
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_in_valid_0 -layer M4 \
    -location "$x $top_cy" -pin_size "0.084 $top_pin_h"
incr idx

# BOTTOM edge: all outputs on M4, extending to die bottom
set idx 0
for {set i 0} {$i < 32} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_out_b_0\[$i\]" -layer M4 \
        -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
    incr idx
}
for {set i 0} {$i < 32} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_out_c_0\[$i\]" -layer M4 \
        -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
    incr idx
}
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_out_control_0_dataflow -layer M4 \
    -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
incr idx
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_out_control_0_propagate -layer M4 \
    -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
incr idx
for {set i 0} {$i < 5} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_out_control_0_shift\[$i\]" -layer M4 \
        -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
    incr idx
}
for {set i 0} {$i < 4} {incr i} {
    set x [expr {$x_start + $idx * $sp2}]
    place_pin -pin_name "io_out_id_0\[$i\]" -layer M4 \
        -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
    incr idx
}
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_out_last_0 -layer M4 \
    -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"
incr idx
set x [expr {$x_start + $idx * $sp2}]
place_pin -pin_name io_out_valid_0 -layer M4 \
    -location "$x $bot_cy" -pin_size "0.084 $bot_pin_h"

puts "Manual pin placement: 172 pins extending to die edges"
