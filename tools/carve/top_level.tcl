# The top level of a parent macro (parent_macro.bzl) after its floorplan,
# the parent and its blocks dissolved: one script, not ORFS's place, CTS
# and global route, which optimise every cell, where here nearly every
# cell is fixed where its macro placed and repaired it. On XSTile the
# flow's place and CTS spent most of their two hours on parasitics
# estimates, repair and legalisation of fixed cells.
#
# The Top is built in two passes. The first, firm, leaves every cell where
# its macro placed it and builds the clock tree over every register and
# the routes between the macros; the end pins of its crossing paths over
# the budget are the second pass's (crossing_ends, TOP_UNFIRM). The
# second starts again from the floorplan: the cells of the paths into
# those ends, their registers with them, are unfirmed (unfirm.tcl),
# placed by global placement with timing and routability driving, and
# repaired; then the tree, the legaliser, which seats them with the clock
# tree's buffers, and global route, as in the first pass.
#
# Each step writes its result, and TOP_FROM resumes after one, so a step
# that fails is run again without the ones before it; TOP_TO stops after
# one, so each step's time and memory are its own process's:
#
#   floorplan  (default) 2_floorplan.odb: the place step next with
#              TOP_UNFIRM, else the clock tree
#   place      3_top_place.odb, TOP_UNFIRM only: the unfirmed cells placed
#              and repaired, place.txt and moved.tsv beside it; run alone
#              (TOP_TO place), its timing settings its own
#   tree       4_top_cts_tree.odb, the tree as built: the legaliser next
#   cts        4_top_cts.odb, legalised: global route next
#   grt        5_top_grt.odb, routed: the crossings, and the clock check
#              when they are timed whole (CROSSING_TXT, no CROSSING_SETS)
#
# Every step's .sdc is the floorplan's, the constraints read: the clock
# period and the false paths the place step times its placement with are
# its own, and reach neither the tree, the legaliser, global route nor
# the crossing report. Under Bazel (parent_macro.bzl) the run writes only
# its last step's design and .sdc to its output directory
# (RUN_OUTPUT_DIR), and TOP_DIR names the directory a later run resumes
# from. A variable is read only in the step that uses it.
#
#   TOP_UNFIRM         the ends file (crossing_ends' ends.tsv); empty or
#                      unset: the firm pass, no place step
#   UNFIRM_TCL         unfirm.tcl, sourced when TOP_UNFIRM is set
#   TOP_UNFIRM_DEEP    place: registers deep past the paths' own (0)
#   TOP_UNFIRM_SIDE    place: the side the depth is taken on, both
#                      (default), back or fwd
#   TOP_CLOCK_PERIOD   place: the period the placement is timed at, the
#                      SDC's by default
#   GPL_KEEP_OVERFLOW  place: global_placement's -keep_resize_below_overflow
#   PLACE_DENSITY, PLACE_DENSITY_LB_ADDON, CELL_PAD_IN_SITES_GLOBAL_PLACEMENT,
#   MIN_PLACE_STEP_COEF, MAX_PLACE_STEP_COEF, GLOBAL_PLACEMENT_ARGS,
#   DONT_USE_CELLS     place: ORFS's, as global_place.tcl reads them
#   HOLES, PARENT_INST place: the blocks' holes and the parent's instance
#                      (u_parent), the region a placed cell ended in
#   CTS_CLUSTER_SIZE   tree: the clock tree's sink clusters
#   TOP_DPL_ARGS       cts: the legaliser's further arguments
#   GLOBAL_ROUTE_ARGS  grt: global_route's arguments
#   SKIP_PIN_ACCESS    grt: 1 when the macros skipped pin access
#   TOP_GRT_ITERATIONS grt: global route's congestion iterations (0)
#   TOP_PARASITICS     the timing's parasitics: global_routing or placement
#   MAX_SKEW_PS        the setup skew the clock check stops over
#   BUDGET_PS          the crossing report's budget
#   CROSSING_TXT       the crossing report (crossing_paths.tcl); none
#                      and no CROSSING_SETS: route only, time nothing
#   TOP_DIR            the directory TOP_FROM reads, RESULTS_DIR by default
#   CLOCK_CHECK, CROSSING_PATHS, CROSSING_CONES  the scripts
#   CROSSING_SETS, CROSSING_JOBS  time sets of macros apart (below)
source $::env(SCRIPTS_DIR)/load.tcl

set steps {floorplan place tree cts grt}
set from [env_var_or_empty TOP_FROM]
if { $from eq "" } {
  set from floorplan
}
if { $from ni $steps } {
  utl::error FLW 27 "top_level: TOP_FROM $from is none of $steps"
}
set todo [lrange $steps [expr { [lsearch -exact $steps $from] + 1 }] end]
set to [env_var_or_empty TOP_TO]
if { $to ne "" } {
  if { $to ni $steps } {
    utl::error FLW 29 "top_level: TOP_TO $to is none of $steps"
  }
  if { $to ni $todo } {
    # nothing would run and nothing be written
    utl::error FLW 139 "top_level: TOP_TO $to is not after TOP_FROM $from"
  }
  set todo [lrange $todo 0 [lsearch -exact $todo $to]]
}
# the step whose design the run hands on
set last_step [lindex $todo end]

set unfirm [env_var_or_empty TOP_UNFIRM]
if { $unfirm ne "" } {
  source $::env(UNFIRM_TCL)
} elseif { $last_step eq "place" } {
  # the first pass has no place step: the run would hand on no design
  utl::error FLW 137 "top_level: TOP_TO place without TOP_UNFIRM, the first pass has no place step"
}
if { "place" in $todo && $unfirm ne "" && $last_step ne "place" } {
  # the place step's clock period and false paths stay in the timer: the
  # steps after it, and a crossing report timed in this process, would
  # take them
  utl::error FLW 138 "top_level: the place step runs alone (TOP_TO place), not\
    with the steps after it, $todo"
}

set odbs {floorplan 2_floorplan.odb place 3_top_place.odb tree 4_top_cts_tree.odb cts 4_top_cts.odb grt 5_top_grt.odb}
if { [env_var_exists_and_non_empty TOP_DIR] } {
  set ::env(RESULTS_DIR) $::env(TOP_DIR)
}
# every checkpoint's .sdc is a copy of the floorplan's (top_checkpoint)
set sdc [sdc_file_of [dict get $odbs $from]]
load_design [dict get $odbs $from] -backing_file $::env(OBJECTS_DIR)/top.db

# each step's checkpoint, to resume from; under Bazel the run's last step
# only, in the run's output directory
proc top_checkpoint { step odb } {
  if { [env_var_exists_and_non_empty RUN_OUTPUT_DIR] } {
    if { $step eq $::last_step } {
      orfs_write_db $::env(RUN_OUTPUT_DIR)/$odb
      # the constraints read, not write_sdc's: what the place step adds to
      # time its placement (TOP_CLOCK_PERIOD, the false paths off the cells
      # that stay) is its own, and in the SDC it would take the macros'
      # own paths out of the crossing report
      file copy -force $::env(RESULTS_DIR)/$::sdc $::env(RUN_OUTPUT_DIR)/[sdc_file_of $odb]
    }
    return
  }
  orfs_write_db $::env(RESULTS_DIR)/$odb
  # the constraints read, as above, not the .sdc orfs_write_db wrote
  file copy -force $::env(RESULTS_DIR)/$::sdc $::env(RESULTS_DIR)/[sdc_file_of $odb]
}

if { "place" in $todo && $unfirm ne "" } {
  set before [unfirm::apply [unfirm::read_ends $unfirm] \
    [unfirm::env_or TOP_UNFIRM_DEEP 0] [unfirm::env_or TOP_UNFIRM_SIDE both]]
  unfirm::placed [unfirm::place] $before
  top_checkpoint place 3_top_place.odb
}
if { "tree" in $todo } {
  repair_clock_inverters
  log_cmd clock_tree_synthesis -sink_clustering_enable -repair_clock_nets \
    -sink_clustering_size $::env(CTS_CLUSTER_SIZE)
  # CTS leaves 24 GB of timing data that no step before global route reads
  sta::network_changed_non_sdc
  top_checkpoint tree 4_top_cts_tree.odb
}
if { "cts" in $todo } {
  # only the clock tree's buffers and the placed unfirmed cells move: the
  # diamond legaliser seats them, the negotiation one repainted 9.4 M fixed
  # cells for over 35 minutes
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
  # the Top never reroutes incrementally; GLOBAL_ROUTE_ARGS is not
  # substituted here, so the backing file is named in the call itself
  log_cmd global_route -congestion_iterations $iterations -no_incremental \
    -backing_file $::env(OBJECTS_DIR)/grt.grid {*}$::env(GLOBAL_ROUTE_ARGS)
  top_checkpoint grt 5_top_grt.odb
  # the unfirm dropped the route of every net on an unfirmed cell; global
  # route, routing the nets without guides (-unguided_only), routes each
  if { $unfirm ne "" } {
    unfirm::unrouted
  }
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
# Each writes CROSSING_TXT.<n>. The clock check (top_clock_check.tcl)
# needs the whole clock network and does not run here: crossing_plan.tcl,
# which loads the routed design whole to draw the sets, stops on a
# register with no clock, and nothing checks the skew.
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
    set base $::env(CROSSING_ODB_DIR)/set_$crossing_set
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
