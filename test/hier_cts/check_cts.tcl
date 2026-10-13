# Reads the CTS result back, as every later stage does, and writes what
# the hierarchical view makes of it: registers with no clock, and pins
# with no hierarchical net on a net that has one.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc

set unclocked 0
foreach error [sta::check_timing_cmd 0 0 0 1 0 0 0] {
  set unclocked [llength [lrange $error 1 end]]
}
set off_modnet 0
set hier_nets 0
foreach net [[ord::get_db_block] getNets] {
  set has_mod_net 0
  set without 0
  foreach iterm [$net getITerms] {
    if { [$iterm getModNet] eq "NULL" } {
      incr without
    } else {
      set has_mod_net 1
    }
  }
  if { $has_mod_net } {
    incr hier_nets
    incr off_modnet $without
  }
}
set registers [llength [all_registers -edge_triggered]]
set f [open [file join $::env(WORK_HOME) $::env(OUTPUT)] w]
puts $f "registers $registers"
puts $f "unclocked $unclocked"
puts $f "hier_nets $hier_nets"
puts $f "off_modnet $off_modnet"
close $f
