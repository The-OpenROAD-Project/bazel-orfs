# Pin partners: which block each block pin talks to. Run in an odb-debug
# session (timing not needed, GUI_TIMING=0) on the parent's synthesis
# ODB, where the hardened blocks are blackbox instances and the parent's
# own logic is flat. For every pin of every block instance: the master
# of the block at the other end of its net when there is one, else
# "logic" (a parent cell) or "port" (a top-level pin). One line per pin
# to PROBE_OUT:
#
#   pin <block master> <pin name> <partner>
#
# The planner reads it to split each block's pin side into segments, one
# per partner, ordered by where the partner sits in the plan, so both
# ends of an interface face each other. Pin placement is a compromise
# between two blocks and belongs to the parent's plan, not to either
# block's own flow.
set out [open $::env(PROBE_OUT) w]
set block [ord::get_db_block]
set n 0
foreach inst [$block getInsts] {
  set master [$inst getMaster]
  if { ![$master isBlock] } { continue }
  set mname [$master getName]
  foreach it [$inst getITerms] {
    set net [$it getNet]
    set partner "unconnected"
    if { $net != "NULL" } {
      set partner "logic"
      foreach other [$net getITerms] {
        if { $other == $it } { continue }
        set oi [$other getInst]
        if { [[$oi getMaster] isBlock] } { set partner [[$oi getMaster] getName]; break }
      }
      if { $partner eq "logic" && [llength [$net getBTerms]] > 0 && [llength [$net getITerms]] == 1 } {
        set partner "port"
      }
    }
    puts $out "pin $mname [[$it getMTerm] getName] $partner"
    incr n
  }
}
close $out
puts "pin partners: $n block pins written to $::env(PROBE_OUT)"
