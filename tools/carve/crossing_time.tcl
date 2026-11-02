# One crossing set of a parent macro's top level, timed on its own: the
# set's design as top_level.tcl cut and wrote it (CROSSING_ODB_DIR), its
# nets whole with their global routes, every cell they reach, the side
# inputs' fan-in and the clock network, so its paths time as in the whole
# design. On the toy (test/parent_macro), written and timed apart, the
# sets report the whole design's paths, slack for slack.
#
#   SET_ODB, SET_SDC   the set's design
#   CROSSING_TXT       the report (crossing_paths.tcl)
#   CROSSING_PATHS     that script
#   TOP_PARASITICS     global_routing (default) or placement
source $::env(SCRIPTS_DIR)/load.tcl
# ORFS's own loading, libraries, derating and layer RC as every stage's,
# from the set's directory
# the set's design, its parasitics read in (SET_SPEF) or estimated here
set ::env(RESULTS_DIR) [file dirname $::env(SET_ODB)]
load_design [file tail $::env(SET_ODB)] [file tail $::env(SET_SDC)]
set parasitics [env_var_or_empty TOP_PARASITICS]
if { $parasitics eq "" } {
  set parasitics global_routing
}
# TOP_MEMORY: resident memory after each phase, to see what to prune
proc memory { phase } {
  if { ![info exists ::env(TOP_MEMORY)] } { return }
  set f [open /proc/self/status]
  foreach line [split [read $f] "\n"] {
    if { [string match "VmRSS:*" $line] || [string match "VmHWM:*" $line] } {
      lappend m [lrange $line 1 1]
    }
  }
  close $f
  puts [format "memory: %-12s rss %.1f GB, peak %.1f GB" $phase \
    [expr { [lindex $m 1] / 1048576.0 }] [expr { [lindex $m 0] / 1048576.0 }]]
}
memory loaded
set_propagated_clock [all_clocks]
if { [info exists ::env(SET_SPEF)] } {
  log_cmd read_spef $::env(SET_SPEF)
} else {
  log_cmd estimate_parasitics -$parasitics
}
memory parasitics
# CONE_MACROS, the set's: the registers no crossing path starts at, the
# side inputs' fan-in, start false paths, so the search propagates no
# arrivals from them (crossing_cones' false_starts)
if { [env_var_exists_and_non_empty CONE_MACROS] } {
  set parent [env_var_or_empty PARENT_INST]
  if { $parent eq "" } {
    set parent u_parent
  }
  set needs [lassign [sta::crossing_cones $::env(CONE_MACROS) $parent 1 1] seeds kept before]
  puts "crossing_cones: $seeds crossing nets, $kept of $before instances kept,\
    [lindex $needs end] of them side-only starts, false paths"
}
# required times are found for the reported endpoints only, by the
# report; finding them everywhere (sta::find_requireds) took set 0 of
# XSTile from 33 to 61 GB in CRPR
if { [info exists ::env(TOP_MEMORY)] } {
  sta::find_delays
  memory delays
  # arrivals alone, before the report enumerates paths: which of the two
  # holds the search's memory
  sta::find_timing_cmd 0
  memory arrivals
  puts "search: [sta::tag_count] tags, [sta::clk_info_count] clock infos,\
    [sta::path_count] paths"
}
set ::crossing_paths_loaded 1
source $::env(CROSSING_PATHS)
memory report
