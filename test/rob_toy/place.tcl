# Places the generated RobState by construction (POST_TAPCELL_TCL): a
# column per bank across the core, the bank's lines in order up its
# column, each line in a band of rows, every cell of an entry in its
# line's band in the order rob_gen.py made it (flops with their logic).
# The cells are spread evenly over the band and skip what tapcell
# placed; they are FIRM through global placement, which places the
# shared logic and the top around them, and unfix.tcl makes them PLACED
# again so repair can resize them and the legaliser move them.
set block [ord::get_db_block]
set core [$block getCoreArea]
set cx0 [$core xMin]
set cx1 [$core xMax]

set rows {}
foreach row [$block getRows] {
  lappend rows [list [lindex [$row getOrigin] 1] $row]
}
set rows [lsort -integer -index 0 $rows]
set nrows [llength $rows]
set site_w [[[lindex $rows 0 1] getSite] getWidth]
# the site grid starts at the rows' origin
set gx [lindex [[lindex $rows 0 1] getOrigin] 0]

# what tapcell placed, per row: x intervals to skip
array set taken {}
foreach inst [$block getInsts] {
  if { ![$inst isFixed] } { continue }
  set box [$inst getBBox]
  lappend taken([$box yMin]) [list [$box xMin] [$box xMax]]
}

# the generated cells by bank and line, in the order they were made
array set cells {}
set banks 0
set lines 0
foreach inst [$block getInsts] {
  if { [regexp {b(\d+)_l(\d+)_c(\d+)} [$inst getName] -> b l c] } {
    lappend cells($b,$l) [list $c $inst]
    set banks [expr { max($banks, $b + 1) }]
    set lines [expr { max($lines, $l + 1) }]
  }
}
if { $banks == 0 } {
  error "place.tcl: no generated cell named b<bank>_l<line>_c<n>"
}

set col_w [expr { ($cx1 - $cx0) / $banks }]
set placed 0
for { set b 0 } { $b < $banks } { incr b } {
  set x0 [expr { $cx0 + $b * $col_w }]
  set x1 [expr { $x0 + $col_w }]
  for { set l 0 } { $l < $lines } { incr l } {
    if { ![info exists cells($b,$l)] } { continue }
    set r0 [expr { $l * $nrows / $lines }]
    set r1 [expr { ($l + 1) * $nrows / $lines }]
    set list [lsort -integer -index 0 $cells($b,$l)]
    set width 0
    foreach e $list {
      incr width [[[lindex $e 1] getMaster] getWidth]
    }
    # the cells spread evenly: a gap after each in proportion to the
    # band's room
    set room [expr { double($x1 - $x0) * ($r1 - $r0) }]
    set stretch [expr { max(1.0, 0.9 * $room / max(1, $width)) }]
    set r $r0
    set x $x0
    foreach e $list {
      set inst [lindex $e 1]
      set w [[$inst getMaster] getWidth]
      while 1 {
        set x [expr { $gx + (($x - $gx + $site_w - 1) / $site_w) * $site_w }]
        if { $x + $w > $x1 } {
          incr r
          set x $x0
          if { $r >= $nrows } {
            error "place.tcl: bank $b line $l does not fit the core"
          }
          continue
        }
        set y [lindex $rows $r 0]
        set clash 0
        if { [info exists taken($y)] } {
          foreach iv $taken($y) {
            if { $x < [lindex $iv 1] && $x + $w > [lindex $iv 0] } {
              set x [lindex $iv 1]
              set clash 1
              break
            }
          }
        }
        if { !$clash } { break }
      }
      set row [lindex $rows $r 1]
      $inst setOrient [$row getOrient]
      $inst setLocation $x $y
      $inst setPlacementStatus FIRM
      lappend taken($y) [list $x [expr { $x + $w }]]
      set x [expr { $x + int($w * $stretch) }]
      incr placed
    }
  }
}
puts "place.tcl: $placed generated cells placed in $banks bank columns of $lines lines"
