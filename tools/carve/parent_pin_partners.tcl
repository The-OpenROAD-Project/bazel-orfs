# The planner's pin partner dump (probe_pin_partners.tcl's format) from a
# parent macro's synthesis, where every block pin is a port of the parent,
# u_<block>__<pin> (evert.tcl): no block is built, so the plan the blocks
# and the parent build from is regenerated without waiting for any of them.
# One line per block pin to PROBE_OUT:
#
#   pin <block> <pin> <partner> <partner pin>
#
# partner is the block at the other end of the parent's net, through
# buffers synthesis put on a feedthrough, else "logic" (a cell of the
# parent's), "port" (one of the design's ports) or "unconnected".
#
#   CARVE_BLOCKS  the blocks, by module
#   PROBE_OUT     the dump
read_db $::env(RESULTS_DIR)/1_synth.odb
set block [ord::get_db_block]

proc block_pin { name } {
  if { [regexp {^u_(.+?)__(.+)$} $name -> m pin] && [lsearch -exact $::env(CARVE_BLOCKS) $m] >= 0 } {
    return [list $m $pin]
  }
  return {}
}

# a one-input, one-output cell, the kind synthesis puts on a feedthrough
proc through { it } {
  set ins {}
  set outs {}
  foreach t [[$it getInst] getITerms] {
    if { [[$t getMTerm] getSigType] ne "SIGNAL" } { continue }
    if { [$t isInputSignal] } { lappend ins $t } elseif { [$t isOutputSignal] } { lappend outs $t }
  }
  if { [llength $ins] == 1 && [llength $outs] == 1 } {
    return [expr { $it eq [lindex $ins 0] ? [lindex $outs 0] : [lindex $ins 0] }]
  }
  return {}
}

# Every net the pin reaches through buffers: a block's port there makes
# that block the partner (as probe_pin_partners.tcl prefers one), else any
# other cell makes it the parent's logic, else a design port.
proc partner_of { bt } {
  set todo [list [$bt getNet]]
  set seen [dict create]
  set logic 0
  set port 0
  while { [llength $todo] > 0 } {
    set net [lindex $todo 0]
    set todo [lrange $todo 1 end]
    if { $net eq "NULL" || [dict exists $seen [$net getName]] } { continue }
    dict set seen [$net getName] 1
    foreach b [$net getBTerms] {
      if { $b eq $bt } { continue }
      set o [block_pin [$b getName]]
      if { $o ne {} } { return $o }
      set port 1
    }
    foreach it [$net getITerms] {
      set next [through $it]
      if { $next eq {} } {
        set logic 1
      } else {
        lappend todo [$next getNet]
      }
    }
  }
  if { $logic } { return {logic -} }
  if { $port } { return {port -} }
  return {unconnected -}
}

set out [open $::env(PROBE_OUT) w]
set n 0
foreach bt [$block getBTerms] {
  set me [block_pin [$bt getName]]
  if { $me eq {} } { continue }
  lassign $me m pin
  lassign [partner_of $bt] partner ppin
  puts $out "pin $m $pin $partner $ppin"
  incr n
}
close $out
puts "parent_pin_partners: $n block pins written to $::env(PROBE_OUT)"
