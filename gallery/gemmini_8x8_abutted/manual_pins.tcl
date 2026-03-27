# Manual pin placement for Tile macro — bypasses place_pins bug.
#
# Places each pin at exact track-grid coordinates with safe offset
# from die edges. Mirrored pins get matching coordinates on opposite edges.
#
# Run via: tmp/gemmini_8x8_abutted/Tile_place_deps/make run \
#   RUN_SCRIPT=$(pwd)/gemmini_8x8_abutted/manual_pins.tcl

source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_1_place_gp_skip_io.odb 2_floorplan.sdc

set block [ord::get_db_block]
set db [ord::get_db]
set tech [$db getTech]

# Die dimensions
set bbox [$block getDieArea]
set die_xlo [ord::dbu_to_microns [$bbox xMin]]
set die_ylo [ord::dbu_to_microns [$bbox yMin]]
set die_xhi [ord::dbu_to_microns [$bbox xMax]]
set die_yhi [ord::dbu_to_microns [$bbox yMax]]

puts "Die: ($die_xlo, $die_ylo) to ($die_xhi, $die_yhi)"

# Track grid: ASAP7 M3/M5 pitch=0.048, offset=0.012
set pitch 0.048
set offset 0.012

# Safe edge offsets — pins inset from die boundary for via access
set edge_inset 0.500  ;# 500nm from edge — plenty of room for vias

# Pin sizes (from ASAP7 M3/M5 min width)
set m3_w 0.018
set m3_h 0.037
set m5_w 0.024
set m5_h 0.084

# Helper: snap to nearest track
proc snap_track {val} {
    set pitch 0.048
    set offset 0.012
    set n [expr {round(($val - $offset) / $pitch)}]
    return [expr {$offset + $n * $pitch}]
}

# Helper: place one pin
proc do_place_pin {name layer x y} {
    set layer_upper [string toupper $layer]
    # Choose pin size based on layer
    # ASAP7 min widths: M2=0.018, M3=0.018, M4=0.024, M5=0.024
    if {$layer_upper eq "M5"} {
        set w 0.024
        set h 0.084
    } elseif {$layer_upper eq "M4"} {
        set w 0.084
        set h 0.024
    } elseif {$layer_upper eq "M3"} {
        set w 0.018
        set h 0.037
    } else {
        set w 0.037
        set h 0.018
    }
    place_pin -pin_name $name -layer $layer_upper -location "$x $y" -pin_size "$w $h"
}

# ========================================
# Pin assignment
# ========================================

# LEFT edge: io_in_a_0[0..7] on M5 (vertical layer, X = die_xlo + inset)
# Use explicit track positions to avoid floating point drift
# Die is 25.920 µm. Track grid: 0.012 + N*0.048
# Left: N=10 → 0.492 (inset ~0.5 µm from X=0)
# Right: N=529 → 25.404 (inset ~0.5 µm from X=25.920)
set left_x 0.492
set right_x_val 25.404
set start_y [snap_track [expr {$die_ylo + 4.0}]]  ;# start 4µm from bottom

puts "Left edge pins at X=$left_x"
for {set i 0} {$i < 8} {incr i} {
    set y [snap_track [expr {$start_y + $i * $pitch * 4}]]
    do_place_pin "io_in_a_0\[$i\]" M5 $left_x $y
    puts "  io_in_a_0\[$i\] at ($left_x, $y)"
}

# RIGHT edge: io_out_a_0[0..7] + clock + io_bad_dataflow on M5
set right_x $right_x_val

puts "Right edge pins at X=$right_x"
for {set i 0} {$i < 8} {incr i} {
    # Mirror Y from left edge
    set y [snap_track [expr {$start_y + $i * $pitch * 4}]]
    do_place_pin "io_out_a_0\[$i\]" M5 $right_x $y
    puts "  io_out_a_0\[$i\] at ($right_x, $y)"
}
# Non-symmetric pins on right edge
set y [snap_track [expr {$start_y + 8 * $pitch * 4}]]
do_place_pin "clock" M5 $right_x $y
puts "  clock at ($right_x, $y)"
set y [snap_track [expr {$start_y + 9 * $pitch * 4}]]
do_place_pin "io_bad_dataflow" M5 $right_x $y
puts "  io_bad_dataflow at ($right_x, $y)"

# TOP edge: io_in_b_0[0..31], io_in_d_0[0..31], control, id, last, valid
# Use M4 (horizontal layer) — safe at top edge
# Top: N=529 → 25.404 (inset ~0.5 µm from Y=25.920)
set top_y 25.404
set start_x [snap_track [expr {$die_xlo + 2.0}]]

puts "Top edge pins at Y=$top_y"
set pin_idx 0
# io_in_b_0[0..31]
for {set i 0} {$i < 32} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_in_b_0\[$i\]" M4 $x $top_y
    incr pin_idx
}
# io_in_d_0[0..31]
for {set i 0} {$i < 32} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_in_d_0\[$i\]" M4 $x $top_y
    incr pin_idx
}
# io_in_control_0_dataflow, propagate
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_in_control_0_dataflow" M4 $x $top_y
incr pin_idx
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_in_control_0_propagate" M4 $x $top_y
incr pin_idx
# io_in_control_0_shift[0..4]
for {set i 0} {$i < 5} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_in_control_0_shift\[$i\]" M4 $x $top_y
    incr pin_idx
}
# io_in_id_0[0..3]
for {set i 0} {$i < 4} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_in_id_0\[$i\]" M4 $x $top_y
    incr pin_idx
}
# io_in_last_0, io_in_valid_0
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_in_last_0" M4 $x $top_y
incr pin_idx
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_in_valid_0" M4 $x $top_y
incr pin_idx

puts "  $pin_idx pins on top edge"

# BOTTOM edge: io_out_b_0[0..31], io_out_c_0[0..31], control, id, last, valid
# Use M4 (horizontal) — mirrored X from top
# Bottom: N=10 → 0.492 (inset ~0.5 µm from Y=0)
set bot_y 0.492

puts "Bottom edge pins at Y=$bot_y"
set pin_idx 0
# io_out_b_0[0..31] — mirrored from io_in_b_0
for {set i 0} {$i < 32} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_out_b_0\[$i\]" M4 $x $bot_y
    incr pin_idx
}
# io_out_c_0[0..31] — mirrored from io_in_d_0
for {set i 0} {$i < 32} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_out_c_0\[$i\]" M4 $x $bot_y
    incr pin_idx
}
# io_out_control_0_dataflow, propagate
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_out_control_0_dataflow" M4 $x $bot_y
incr pin_idx
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_out_control_0_propagate" M4 $x $bot_y
incr pin_idx
# io_out_control_0_shift[0..4]
for {set i 0} {$i < 5} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_out_control_0_shift\[$i\]" M4 $x $bot_y
    incr pin_idx
}
# io_out_id_0[0..3]
for {set i 0} {$i < 4} {incr i} {
    set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
    do_place_pin "io_out_id_0\[$i\]" M4 $x $bot_y
    incr pin_idx
}
# io_out_last_0, io_out_valid_0
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_out_last_0" M4 $x $bot_y
incr pin_idx
set x [snap_track [expr {$start_x + $pin_idx * $pitch * 2}]]
do_place_pin "io_out_valid_0" M4 $x $bot_y
incr pin_idx

puts "  $pin_idx pins on bottom edge"

# Write result
puts ""
puts "=== Manual pin placement complete ==="
puts "Left:   8 pins (io_in_a) on M5 at X=$left_x"
puts "Right:  10 pins (io_out_a + clock + io_bad_dataflow) on M5 at X=$right_x"
puts "Top:    $pin_idx pins on M4 at Y=$top_y"
puts "Bottom: $pin_idx pins on M4 at Y=$bot_y"
puts "Edge inset: ${edge_inset} µm (safe for via access)"

report_design_area

orfs_write_db $::env(RESULTS_DIR)/3_2_place_iop.odb
