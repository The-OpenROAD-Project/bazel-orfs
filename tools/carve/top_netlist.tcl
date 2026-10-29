# The top level of a parent macro: the design's ports, the parent and the
# blocks, instances only. The parent's ports are read from its synthesis
# (evert.tcl named each block pin's u_<master>__<pin>), the blocks' pins
# from the plan's pin tables; a block pin the parent has no port for is
# left open, and the blocks' clock pins are on the design's clock.
#
#   CARVE_BLOCKS  the blocks, by module
#   CARVE_CLOCKS  the blocks' clock pins, by name
#   CLOCK_PORT    the design's clock port
#   PLAN_PINS     each block's plan pins file
#   TOP_NAME      the top level's module
#   TOP_V         the netlist written
read_db $::env(RESULTS_DIR)/1_synth.odb
set block [ord::get_db_block]
set parent [$block getName]

proc esc { s } {
  if { [regexp {^[A-Za-z_][A-Za-z0-9_]*$} $s] } { return $s }
  return "\\$s "
}

# a bus's bits, by name: base -> {lo hi}; a scalar is itself
proc buses { names } {
  set out [dict create]
  foreach n $names {
    if { [regexp {^(.*)\[(\d+)\]$} $n -> base bit] } {
      if { [dict exists $out $base] } {
        lassign [dict get $out $base] lo hi
        dict set out $base [list [expr { min($lo, $bit) }] [expr { max($hi, $bit) }]]
      } else {
        dict set out $base [list $bit $bit]
      }
    } else {
      dict set out $n {}
    }
  }
  return $out
}

set ::plan_pins_only 1
foreach f $::env(PLAN_PINS) {
  source $f
}

set dir [dict create]
set own {}
set to_block {}
foreach bt [$block getBTerms] {
  set n [$bt getName]
  dict set dir $n [string map {INPUT input OUTPUT output INOUT inout} [$bt getIoType]]
  if { [regexp {^u_([^_].*?)__} $n -> m] && [lsearch -exact $::env(CARVE_BLOCKS) $m] >= 0 } {
    lappend to_block $n
  } else {
    lappend own $n
  }
}
if { [lsearch -exact $own $::env(CLOCK_PORT)] < 0 } {
  utl::error FLW 40 "top_netlist: $parent has no clock port $::env(CLOCK_PORT)"
}

set f [open $::env(TOP_V) w]
set ownbus [buses $own]
puts $f "module [esc $::env(TOP_NAME)] ([join [lmap b [dict keys $ownbus] { esc $b }] {, }]);"
proc decl { f kind b range d } {
  if { $range eq {} } {
    puts $f "  $kind [esc $b];"
  } else {
    puts $f "  $kind \[[lindex $range 1]:[lindex $range 0]\] [esc $b];"
  }
}
dict for {b range} $ownbus {
  set n [expr { $range eq {} ? $b : "$b\[[lindex $range 0]\]" }]
  decl $f [dict get $dir $n] $b $range {}
}
set blockbus [buses $to_block]
dict for {b range} $blockbus {
  decl $f wire $b $range {}
}
puts $f "  [esc $parent] u_parent ("
set items {}
dict for {b range} $ownbus { lappend items [format "    .%s(%s)" [esc $b] [esc $b]] }
dict for {b range} $blockbus { lappend items [format "    .%s(%s)" [esc $b] [esc $b]] }
puts $f "[join $items ",\n"]\n  );"

set open 0
foreach m $::env(CARVE_BLOCKS) {
  set pins {}
  foreach {pin layer x y w h} $::plan_pins($m) { lappend pins $pin }
  set items {}
  dict for {b range} [buses $pins] {
    if { [lsearch -exact $::env(CARVE_CLOCKS) $b] >= 0 } {
      lappend items [format "    .%s(%s)" [esc $b] [esc $::env(CLOCK_PORT)]]
      continue
    }
    set w "u_${m}__$b"
    if { ![dict exists $blockbus $w] } {
      incr open
      continue
    }
    if { $range ne [dict get $blockbus $w] } {
      utl::error FLW 41 "top_netlist: $m/$b is bits $range in the plan, [dict get $blockbus $w] at the parent"
    }
    lappend items [format "    .%s(%s)" [esc $b] [esc $w]]
  }
  puts $f "  [esc $m] [esc u_$m] (\n[join $items ",\n"]\n  );"
}
puts $f "endmodule"
close $f
puts "top_netlist: $::env(TOP_NAME): $parent and [llength $::env(CARVE_BLOCKS)] blocks, [llength $to_block] block pins through the parent, $open block pins open"
