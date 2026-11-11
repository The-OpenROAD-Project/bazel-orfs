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
# that fails is run again without the ones before it; TOP_TO stops after
# one, so each step's time and memory are its own process's:
#
#   floorplan  (default) 2_floorplan.odb: the clock tree first
#   place      3_top_place.odb, TOP_FLATTEN only: the boundary logic placed
#   tree       4_top_cts_tree.odb, the tree as built: the legaliser next
#   cts        4_top_cts.odb, the tree legalised: global route next
#   grt        5_top_grt.odb, routed: the clock check and crossings
#
# TOP_FLATTEN names the macros whose boundary logic the top level takes
# over ("all"): each part's in2reg, reg2out and in2out logic up to the
# first register, the cells crossing_cones' flatten mode makes movable,
# is placed again and repaired with the crossings whole, the clock tree
# is built over it, and its nets are routed; the macros'
# register-to-register logic and their registers stay where their macros
# placed and routed them.
#
# Under Bazel (parent_macro.bzl) the run writes only the routed design,
# 5_top_grt.odb and .sdc, to its output directory (RUN_OUTPUT_DIR), and
# TOP_DIR names the directory a later run resumes from.
#
#   TOP_FLATTEN        the macros whose boundary logic the top level takes
#   PARENT_INST        the parent's instance (u_parent)
#   TOP_GPL_ARGS       global_placement's further arguments (TOP_FLATTEN)
#   TOP_SKIP_GPL       1: the boundary logic stays where its macros placed
#                      it; repair and the legaliser move what they must
#   TOP_CLOCK_PERIOD   the period the Top repairs to (TOP_FLATTEN), the
#                      SDC's by default: repair works on failing paths only
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

set steps {floorplan place tree cts grt}
set from [env_var_or_empty TOP_FROM]
if { $from eq "" } {
  set from floorplan
}
if { $from ni $steps } {
  utl::error FLW 27 "top_level: TOP_FROM $from is none of $steps"
}
set odbs {floorplan 2_floorplan.odb place 3_top_place.odb tree 4_top_cts_tree.odb cts 4_top_cts.odb grt 5_top_grt.odb}
if { [env_var_exists_and_non_empty TOP_DIR] } {
  set ::env(RESULTS_DIR) $::env(TOP_DIR)
}
# every checkpoint's .sdc is a copy of the floorplan's (top_checkpoint)
set sdc [sdc_file_of [dict get $odbs $from]]
load_design [dict get $odbs $from] -backing_file $::env(OBJECTS_DIR)/top.db
set todo [lrange $steps [expr { [lsearch -exact $steps $from] + 1 }] end]
set to [env_var_or_empty TOP_TO]
if { $to ne "" } {
  if { $to ni $steps } {
    utl::error FLW 29 "top_level: TOP_TO $to is none of $steps"
  }
  set todo [lrange $todo 0 [lsearch -exact $todo $to]]
}

# each step's checkpoint, to resume from; under Bazel the routed design
# only, in the run's output directory
proc top_checkpoint { step odb } {
  if { [env_var_exists_and_non_empty RUN_OUTPUT_DIR] } {
    if { $step eq "grt" } {
      orfs_write_db $::env(RUN_OUTPUT_DIR)/$odb
      # the constraints read, not write_sdc's: what the flattened Top's
      # repair adds (TOP_CLOCK_PERIOD, the false path starts of every
      # register no crossing starts at) is the repair's own, and in the
      # SDC it took the macros' own paths out of the crossing report
      file copy -force $::env(RESULTS_DIR)/$::sdc $::env(RUN_OUTPUT_DIR)/5_top_grt.sdc
    }
    return
  }
  orfs_write_db $::env(RESULTS_DIR)/$odb
  # the constraints read, as above, not the .sdc orfs_write_db wrote
  file copy -force $::env(RESULTS_DIR)/$::sdc $::env(RESULTS_DIR)/[sdc_file_of $odb]
}

set flatten [env_var_or_empty TOP_FLATTEN]
set parent [env_var_or_empty PARENT_INST]
if { $parent eq "" } {
  set parent u_parent
}
if { "place" in $todo && $flatten ne "" } {
  # no path group through the crossing nets: repair removes some of them,
  # and the group's net set would hold them dangling
  set needs [lassign [sta::crossing_cones $flatten $parent 1 0 "" 1] \
    seeds kept before]
  set at [lsearch -exact $needs flatten]
  puts "top_level: $seeds crossing nets, [lindex $needs [expr { $at + 1 }]] of\
    $before cells movable, [lindex $needs [expr { $at + 2 }]] nets to route"
  # from where their macros placed them: the macros' placement is the
  # start a global placement would spend its first iterations finding.
  # Wirelength-driven, it re-spread the long buffer chains the macros had
  # built along a crossing: on XSTile with Flt flattened, Rob -> Flt
  # 2,706 -> 3,710 ps, 122 of the worst path's 184 pins on moved cells
  if { ![env_var_equals TOP_SKIP_GPL 1] } {
    log_cmd global_placement -skip_initial_place {*}[env_var_or_empty TOP_GPL_ARGS]
  }
  log_cmd estimate_parasitics -placement
  log_cmd repair_design
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
  # only the clock tree's buffers move: the diamond legaliser seats them,
  # the negotiation one repainted 9.4 M fixed cells for over 35 minutes
  log_cmd detailed_placement -use_diamond_legalizer {*}[env_var_or_empty TOP_DPL_ARGS]
  # the cells it can move; the fixed ones are their macros' (on XSTile a
  # register file of Ftq's fails the padding check, inside Ftq)
  log_cmd check_placement -placeable -verbose
  if { $flatten ne "" } {
    # the crossings whole, the boundary logic the only cells to change
    set period [env_var_or_empty TOP_CLOCK_PERIOD]
    if { $period ne "" } {
      foreach clock [all_clocks] {
        create_clock -name [get_name $clock] -period $period \
          [get_property $clock sources]
      }
    }
    # the crossing paths only: every register no crossing path starts at
    # is a false path start for the repair, and every one no crossing path
    # ends at a false path end, so the macros' own paths are not timed
    # (with starts alone 83,649 endpoints still failed, the worst a
    # Frontend SRAM's address from a register that also launches a
    # crossing). Timed whole, XSTile's flattened Top (Flt) needed 118 GB
    # and 120 GB of swap, and setup repair spent 2.6 hours on 133,858
    # failing endpoints of the macros' own paths, which it may not change
    # (973 VT swaps, 1 buffer). repair_timing -path_group knows only
    # reg2reg, in2reg, reg2out, in2out and gated_clock, no group through
    # the crossings.
    # and the path group `crossing` through the crossing nets, the only
    # paths repair works on: false starts and ends scope repair by
    # register, and a register that starts or ends a crossing also starts
    # or ends its macro's own paths; the group scopes it by path. On XSTile
    # with all six flattened nearly every failing endpoint is a crossing's
    # anyway (117,057 of 118,489). 0210 keeps the group sound when repair
    # deletes one of its nets, 0209 lets repair_timing -path_group take it.
    set needs [lassign [sta::crossing_cones $flatten $parent 1 2 crossing] seeds kept before]
    puts "top_level: crossing paths only, [lindex $needs [expr { [lsearch -exact $needs false] + 1 }]]\
      registers no crossing starts at and\
      [lindex $needs [expr { [lsearch -exact $needs false_ends] + 1 }]] no crossing ends at\
      made false path starts and ends"
    set_propagated_clock [all_clocks]
    log_cmd estimate_parasitics -placement
    log_cmd repair_timing -setup -hold -repair_tns 100 -path_group crossing
    log_cmd detailed_placement -use_diamond_legalizer {*}[env_var_or_empty TOP_DPL_ARGS]
    log_cmd check_placement -placeable -verbose
  }
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
