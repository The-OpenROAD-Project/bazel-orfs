# A block's pin contract: PIN_GROUPS is a list of <glob> <side> pairs, each
# putting the signal pins whose name matches the glob on that side (left,
# right, top, bottom), or on a stretch of it as <side>:<from>-<to> in um. Pins no glob names are free: the pin placer puts them
# where the block's own placement wants them, which is the choice a pin
# trap is built to catch. An empty PIN_GROUPS leaves every pin free.
set block [ord::get_db_block]
set groups [expr { [info exists ::env(PIN_GROUPS)] ? $::env(PIN_GROUPS) : "" }]
if { [llength $groups] % 2 != 0 } {
  error "pins.tcl: PIN_GROUPS must be <glob> <side> pairs, got '$groups'"
}
foreach {glob side} $groups {
  set region $side:*
  if { [regexp {^(left|right|top|bottom):([0-9.]+)-([0-9.]+)$} $side - edge lo hi] } {
    set region $edge:$lo-$hi
  } elseif { $side ni {left right top bottom} } {
    error "pins.tcl: side '$side' for '$glob' is not left, right, top, bottom or <side>:<from>-<to>"
  }
  set names {}
  foreach bterm [$block getBTerms] {
    if { [$bterm getSigType] ne "SIGNAL" } { continue }
    if { [string match $glob [$bterm getName]] } { lappend names [$bterm getName] }
  }
  if { [llength $names] == 0 } {
    error "pins.tcl: '$glob' names no signal pin of [$block getName]"
  }
  set_io_pin_constraint -region $region -pin_names $names
  puts "pins.tcl: [llength $names] pins '$glob' on $side"
}
