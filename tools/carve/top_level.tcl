# The top level of a parent macro (parent_macro.bzl) after its floorplan,
# the parent and its blocks dissolved: one script, not ORFS's place, CTS
# and global route, which optimise cells and this top level has none to
# optimise. Every cell is fixed where its macro placed and repaired it;
# what is left is the clock tree over every register and the routes
# between the macros. On XSTile the flow's place and CTS spent most of
# their two hours on parasitics estimates, repair and legalisation of
# fixed cells.
#
# Each step writes its result, and TOP_FROM resumes after one, so a step
# that fails is run again without the ones before it:
#
#   floorplan  (default) 2_floorplan.odb: the clock tree first
#   tree       4_top_cts_tree.odb, the tree as built: the legaliser next
#   cts        4_top_cts.odb, the tree legalised: global route next
#   grt        5_top_grt.odb, routed: the clock check and crossings
#
# Under Bazel (parent_macro.bzl) the run writes only the routed design,
# 5_top_grt.odb and .sdc, to its output directory (RUN_OUTPUT_DIR), and
# TOP_DIR names the directory a later run resumes from.
#
#   CTS_CLUSTER_SIZE   the clock tree's sink clusters
#   TOP_DPL_ARGS       the legaliser's further arguments
#   GLOBAL_ROUTE_ARGS  global_route's arguments
#   SKIP_PIN_ACCESS    1 when the macros skipped pin access
#   TOP_GRT_ITERATIONS global route's congestion iterations (0)
#   TOP_PARASITICS     the timing's parasitics: global_routing or placement
#   MAX_SKEW_PS        the setup skew the clock check stops over
#   BUDGET_PS          the crossing report's budget
#   CROSSING_TXT       the crossing report (crossing_paths.tcl); none
#                      and no CROSSING_SETS: route only, time nothing
#   TOP_DIR            the directory TOP_FROM reads, RESULTS_DIR by default
#   CLOCK_CHECK, CROSSING_PATHS, CROSSING_CONES  the scripts
#   CROSSING_SETS, CROSSING_JOBS  time sets of macros apart (below)
source $::env(SCRIPTS_DIR)/load.tcl

set steps {floorplan tree cts grt}
set from [env_var_or_empty TOP_FROM]
if { $from eq "" } {
  set from floorplan
}
if { $from ni $steps } {
  utl::error FLW 27 "top_level: TOP_FROM $from is none of $steps"
}
set odbs {floorplan 2_floorplan.odb tree 4_top_cts_tree.odb cts 4_top_cts.odb grt 5_top_grt.odb}
set sdc 2_floorplan.sdc
if { [env_var_exists_and_non_empty TOP_DIR] } {
  set ::env(RESULTS_DIR) $::env(TOP_DIR)
  set sdc 5_top_grt.sdc
}
load_design [dict get $odbs $from] $sdc
set todo [lrange $steps [expr { [lsearch -exact $steps $from] + 1 }] end]

# each step's checkpoint, to resume from; under Bazel the routed design
# only, in the run's output directory
proc top_checkpoint { step odb } {
  if { [env_var_exists_and_non_empty RUN_OUTPUT_DIR] } {
    if { $step eq "grt" } {
      orfs_write_db $::env(RUN_OUTPUT_DIR)/$odb
      write_sdc -no_timestamp $::env(RUN_OUTPUT_DIR)/5_top_grt.sdc
    }
    return
  }
  orfs_write_db $::env(RESULTS_DIR)/$odb
}

if { "tree" in $todo } {
  repair_clock_inverters
  log_cmd clock_tree_synthesis -sink_clustering_enable -repair_clock_nets \
    -sink_clustering_size $::env(CTS_CLUSTER_SIZE)
  top_checkpoint tree 4_top_cts_tree.odb
}
if { "cts" in $todo } {
  # only the clock tree's buffers move: the diamond legaliser seats them,
  # the negotiation one repainted 9.4 M fixed cells for over 35 minutes
  log_cmd detailed_placement -use_diamond_legalizer {*}[env_var_or_empty TOP_DPL_ARGS]
  # the cells it can move; the fixed ones are their macros' (on XSTile a
  # register file of Ftq's fails the padding check, inside Ftq)
  log_cmd check_placement -placeable -verbose
  top_checkpoint cts 4_top_cts.odb
}
if { "grt" in $todo } {
  # as the macros did: their guides end at access points if they ran
  # pin access, at pin shape centres if not (XiangShan's skip it, DRT-0073
  # on generated macro pins); on the toy, guides meeting pins they were
  # not routed to cost 3,433 of 10,464 nets their guides
  if { ![env_var_equals SKIP_PIN_ACCESS 1] } {
    log_cmd pin_access
  }
  # route 0 by default, as the blocks route: the overflow is where the
  # macros' own kept guides meet (XSTile: 4,200 to 7,200 on edges of 4,000
  # along Bpu's and Ftq's row), which no rip-up of the top level's nets
  # moves; 30 iterations would take hours on it
  set iterations [env_var_or_empty TOP_GRT_ITERATIONS]
  if { $iterations eq "" } {
    set iterations 0
  }
  log_cmd global_route -congestion_iterations $iterations {*}$::env(GLOBAL_ROUTE_ARGS)
  top_checkpoint grt 5_top_grt.odb
}

# XSTile's top level ran out of memory timing on global-routing
# parasitics, 8.7 M nets' RC networks, past 62 GB and 220 GB of swap;
# TOP_PARASITICS=placement times it on placement's estimate instead
set parasitics [env_var_or_empty TOP_PARASITICS]
if { $parasitics eq "" } {
  set parasitics global_routing
}

if {
  ![env_var_exists_and_non_empty CROSSING_SETS]
  && ![env_var_exists_and_non_empty CROSSING_TXT]
} {
  return
}
if { ![env_var_exists_and_non_empty CROSSING_SETS] } {
  set_propagated_clock [all_clocks]
  log_cmd estimate_parasitics -$parasitics
  source $::env(CLOCK_CHECK)
  set ::crossing_paths_loaded 1
  source $::env(CROSSING_PATHS)
  return
}

# CROSSING_SETS: a file, one set of macros per line. Each set is timed in
# a copy-on-write child of this process, cut down to its crossing cones
# (crossing_cones.tcl), so the routed design is loaded once and each
# child's memory is its own set's; CROSSING_JOBS of them at a time (1).
# Each writes CROSSING_TXT.<n>; the clock check needs the whole clock
# network, so a child reports its setup skew instead.
source $::env(ORFS_FORK_TCL)
set f [open $::env(CROSSING_SETS)]
set sets {}
foreach line [split [read $f] "\n"] {
  if { [string trim $line] ne "" && ![string match "#*" $line] } {
    lappend sets [string trim $line]
  }
}
close $f
set jobs [env_var_or_empty CROSSING_JOBS]
if { $jobs eq "" } {
  set jobs 1
}
set crossing_txt [env_var_or_empty CROSSING_TXT]
# under Bazel the sets are written to the run's output directory
if {
  ![env_var_exists_and_non_empty CROSSING_ODB_DIR]
  && [env_var_exists_and_non_empty RUN_OUTPUT_DIR]
} {
  set ::env(CROSSING_ODB_DIR) $::env(RUN_OUTPUT_DIR)
}
set statuses [fork -jobs $jobs crossing_set [lsearch -all $sets *] {
  set ::env(CONE_MACROS) [lindex $sets $crossing_set]
  set ::env(CROSSING_TXT) $crossing_txt.$crossing_set
  source $::env(CROSSING_CONES)
  if { [env_var_exists_and_non_empty CROSSING_ODB_DIR] } {
    # cut and written only, timed apart (crossing_time.tcl): a child's
    # deletions copy most of the loaded design's pages (42 GB on XSTile),
    # so timing in it holds one set at a time; a fresh process loading
    # the set's own design holds that set only
    # the set as it is timed: its nets' global-route parasitics as SPEF,
    # then its design without the routes and the power grid (the small
    # set's 19 GB load) and so without global route's grid to read them
    # back (its 38 GB); names stay the design's, so the SPEF's match
    set base $::env(CROSSING_ODB_DIR)/set.$crossing_set
    log_cmd estimate_parasitics -$parasitics -spef_file $base.spef
    puts "crossing_strip: [sta::crossing_strip] (guides, special wires) removed"
    write_db $base.odb
    write_sdc -no_timestamp $base.sdc
    return
  }
  set_propagated_clock [all_clocks]
  log_cmd estimate_parasitics -$parasitics
  set ::crossing_paths_loaded 1
  source $::env(CROSSING_PATHS)
}]
dict for {n code} $statuses {
  if { $code != 0 } {
    utl::error FLW 28 "top_level: crossing set $n ([lindex $sets $n]) exited $code"
  }
}
