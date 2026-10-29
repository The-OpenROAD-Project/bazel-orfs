# One crossing set in the web GUI: the set's design as top_level.tcl cut
# and wrote it (CROSSING_ODB_DIR), its parasitics read from SPEF, timed as
# crossing_time.tcl times it, then served by the odb-debug daemon. The
# path group "crossing" holds exactly the paths not contained in one
# macro, each crossing a net between two; pick it in the GUI's path
# group filter. Registers only side inputs reach start false paths, so
# the other paths left are few.
#
#   SET_ODB, SET_SDC, SET_SPEF  the set's design (no SPEF: estimated here)
#   CONE_MACROS                 the set's macros
#   ODB_DEBUG_DIR               the daemon's directory (daemon.tcl)
source $::env(SCRIPTS_DIR)/load.tcl
set ::env(RESULTS_DIR) [file dirname $::env(SET_ODB)]
load_design [file tail $::env(SET_ODB)] [file tail $::env(SET_SDC)]
set_propagated_clock [all_clocks]
if { [env_var_exists_and_non_empty SET_SPEF] } {
  log_cmd read_spef $::env(SET_SPEF)
} else {
  log_cmd estimate_parasitics -global_routing
}
set parent [env_var_or_empty PARENT_INST]
if { $parent eq "" } {
  set parent u_parent
}
set needs [lassign [sta::crossing_cones $::env(CONE_MACROS) $parent 1 1 crossing] \
  seeds kept before]
puts "crossing_gui: $seeds crossing nets in path group crossing, $kept instances,\
  [lindex $needs end-2] side-only starts false-pathed"
# timing found before the link is handed out, so no click waits on it
log_cmd sta::find_timing_cmd 0
source $::env(ODB_DEBUG_DAEMON)
