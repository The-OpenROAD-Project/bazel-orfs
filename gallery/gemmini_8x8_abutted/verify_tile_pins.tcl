# Verify Tile macro pin placement for abutment.
#
# Uses ODB API directly (no get_ports — design is loaded via read_db).

read_db $::env(ODB_FILE)

set db [ord::get_db]
set block [[$db getChip] getBlock]
set bbox [$block getDieArea]
set die_xlo [$bbox xMin]
set die_xhi [$bbox xMax]
set die_ylo [$bbox yMin]
set die_yhi [$bbox yMax]
set dbu_to_um [ord::dbu_to_microns 1]

puts "Die area: [expr $die_xlo * $dbu_to_um] [expr $die_ylo * $dbu_to_um] [expr $die_xhi * $dbu_to_um] [expr $die_yhi * $dbu_to_um] µm"

# Classify pins by edge
set left_pins {}
set right_pins {}
set top_pins {}
set bottom_pins {}
set errors 0

foreach bterm [$block getBTerms] {
    set name [$bterm getName]
    set bpins [$bterm getBPins]
    if {[llength $bpins] == 0} continue

    set bpin [lindex $bpins 0]
    set boxes [$bpin getBoxes]
    if {[llength $boxes] == 0} continue

    set box [lindex $boxes 0]
    set x [expr {([$box xMin] + [$box xMax]) / 2}]
    set y [expr {([$box yMin] + [$box yMax]) / 2}]

    # Classify by proximity to die edge
    set tol_x [expr {($die_xhi - $die_xlo) / 5}]
    set tol_y [expr {($die_yhi - $die_ylo) / 5}]

    if {$x <= [expr {$die_xlo + $tol_x}]} {
        lappend left_pins [list $name $x $y]
    } elseif {$x >= [expr {$die_xhi - $tol_x}]} {
        lappend right_pins [list $name $x $y]
    } elseif {$y >= [expr {$die_yhi - $tol_y}]} {
        lappend top_pins [list $name $x $y]
    } elseif {$y <= [expr {$die_ylo + $tol_y}]} {
        lappend bottom_pins [list $name $x $y]
    } else {
        puts "ERROR: pin $name not on any edge (x=$x y=$y)"
        incr errors
    }
}

puts ""
puts "Pin counts per edge:"
puts "  Left:   [llength $left_pins]"
puts "  Right:  [llength $right_pins]"
puts "  Top:    [llength $top_pins]"
puts "  Bottom: [llength $bottom_pins]"
puts ""

# List pins per edge
puts "Left pins:"
foreach p [lsort -index 0 $left_pins] { puts "  [lindex $p 0]" }
puts "Right pins:"
foreach p [lsort -index 0 $right_pins] { puts "  [lindex $p 0]" }
puts "Top pins:"
foreach p [lsort -index 0 $top_pins] { puts "  [lindex $p 0]" }
puts "Bottom pins:"
foreach p [lsort -index 0 $bottom_pins] { puts "  [lindex $p 0]" }

# Check expected assignments
puts ""
puts "Checking edge assignments..."

foreach p $left_pins {
    set name [lindex $p 0]
    if {![string match "io_in_a_*" $name]} {
        puts "ERROR: unexpected left pin: $name"
        incr errors
    }
}

foreach p $right_pins {
    set name [lindex $p 0]
    if {![string match "io_out_a_*" $name]} {
        puts "ERROR: unexpected right pin: $name"
        incr errors
    }
}

foreach p $top_pins {
    set name [lindex $p 0]
    if {![string match "io_in_*" $name]} {
        puts "ERROR: unexpected top pin: $name (expected io_in_*)"
        incr errors
    }
}

foreach p $bottom_pins {
    set name [lindex $p 0]
    set ok 0
    if {[string match "io_out_*" $name]} { set ok 1 }
    if {$name eq "clock"} { set ok 1 }
    if {$name eq "io_bad_dataflow"} { set ok 1 }
    if {!$ok} {
        puts "ERROR: unexpected bottom pin: $name"
        incr errors
    }
}

# Check left-right Y mirroring
puts ""
puts "Checking left↔right Y mirroring..."
set ls [lsort -index 2 -integer $left_pins]
set rs [lsort -index 2 -integer $right_pins]
if {[llength $ls] == [llength $rs]} {
    for {set i 0} {$i < [llength $ls]} {incr i} {
        set ly [lindex [lindex $ls $i] 2]
        set ry [lindex [lindex $rs $i] 2]
        if {$ly != $ry} {
            puts "  MISMATCH: [lindex [lindex $ls $i] 0] y=$ly vs [lindex [lindex $rs $i] 0] y=$ry"
            incr errors
        }
    }
    if {$errors == 0} { puts "  All [llength $ls] left↔right pin pairs have matching Y" }
} else {
    puts "  ERROR: left ([llength $ls]) and right ([llength $rs]) counts differ"
    incr errors
}

puts ""
if {$errors == 0} {
    puts "PASS: All pin checks passed"
} else {
    puts "FAIL: $errors errors"
}
