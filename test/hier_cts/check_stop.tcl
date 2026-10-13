# The CTS stage's stop (patches/0114) passes the database CTS wrote and
# fires once a register's clock pin is taken off its hierarchical net.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc

set f [open [file join $::env(WORK_HOME) $::env(OUTPUT)] w]
puts $f "as_written [catch { check_hier_clock_nets }]"

set taken ""
foreach net [[ord::get_db_block] getNets] {
  if { [$net getSigType] != "CLOCK" } {
    continue
  }
  foreach iterm [$net getITerms] {
    if { [$iterm getModNet] != "NULL" && [$iterm isInputSignal] } {
      set taken [$iterm getName]
      $iterm disconnectDbModNet
      break
    }
  }
  if { $taken != "" } {
    break
  }
}
set fired [catch { check_hier_clock_nets } message]
puts $f "taken $taken"
puts $f "fired $fired"
puts $f "names_it [string match "*$taken*" $message]"
close $f
