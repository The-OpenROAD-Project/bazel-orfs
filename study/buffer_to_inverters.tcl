# A/B study of OpenROAD PR 10662 (rsz: BufferToInverters move), as a
# fork/join walk over the global-route incremental-repair phase.
#
# Which binary runs the walk is chosen OUTSIDE this script (fork cannot
# swap the executable mid-process), so an arm is one invocation with a
# different OPENROAD_EXE. Everything below is identical across arms:
#
#   base      the pull request's merge base
#   pr        base + patches/openroad-10662-buffer-to-inverters.patch
#   completed pr + patches/openroad-10662-review-completion.patch
#
# WHERE THE FORK POINT IS, AND WHY
#
# The move under test is a repair_timing move, so the study varies repair
# configurations. Measured on asap7/riscv32i, a leaf that ran cts+grt
# whole cost 453s of which only the design load -- ~1% -- was shared;
# fork.md is explicit that fork earns its keep through the shared prefix,
# and at that fork point it did not.
#
# So the prefix is everything up to and including global_route (CTS, the
# post-CTS repair, pin_access, routing: ~270s, run once) and the leaf is
# the incremental repair phase (~183s). That needs ORFS to expose a seam
# between routing and repair, which patches/0050 adds as
# GRT_REPAIR_HOOK_TCL.
#
# CONSEQUENCE FOR THE DIMENSIONS: only knobs that act at the post-GR
# repair belong inside the fork. The clock period must be set before CTS,
# so it is an outer dimension -- one invocation per period -- not a
# forked one. Setting it after routing would constrain a design that had
# already been placed, routed and CTS'd against a different target.
#
# WHAT THIS MEASURES, AND WHAT IT CANNOT
#
# Only the post-GR repair. The pull request claims an average improvement
# "in post-CTS and post-GRT timing repair"; forking at CTS instead would
# forfeit the shared routing prefix and roughly triple the cost, so the
# post-CTS half is not measured and the report must say so. The
# OPT_POST_GRT_WNS pass is also out of reach: it hardcodes
# -sequence "vt_swap reroute", so the move can never run there whatever
# SETUP_MOVE_SEQUENCE says.
#
# KEEP_VARS=1 is required: erase_non_stage_variables would otherwise strip
# the per-leaf variables the leaves set.

source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc

source $::env(ORFS_FORK_TCL)

set ::study_out $::env(RESULTS_OUT)
set ::study_arm $::env(STUDY_ARM)
set ::study_design $::env(STUDY_DESIGN)
set ::period_scale $::env(STUDY_PERIOD_SCALE)
file mkdir $::study_out

# The move sequences under test. "stock" is the default sequence spelled
# out explicitly -- SetupLegacyBase builds exactly this when -sequence is
# absent -- so every leaf goes down the same code path and the arms differ
# only in the moves named.
#
# "stock_again" is the SAME sequence as "stock", deliberately. Two leaves
# with an identical configuration give the noise floor, and without one a
# per-design delta cannot be told from run-to-run variation. That is not
# a hypothetical: a maintainer ran this pull request's sibling study on
# the project's own CI and got "some designs showed better WNS while some
# other designs showed worse", which is what a study without a floor
# always produces.
#
# The move is appended, not inserted: the pull request's own claim is
# about appending it to the default sequence.
set ::sequences [dict create \
  stock       "unbuffer,vt_swap,sizeup,swap,buffer,clone,split" \
  stock_again "unbuffer,vt_swap,sizeup,swap,buffer,clone,split" \
  with_move   "unbuffer,vt_swap,sizeup,swap,buffer,clone,split,buffer_to_inverters"]

proc study_dim { var default } {
  if { [info exists ::env($var)] && $::env($var) ne "" } {
    return [split $::env($var) ","]
  }
  return $default
}

set ::dim_sequence [study_dim STUDY_SEQUENCES {stock stock_again with_move}]
set ::dim_margin [study_dim STUDY_MARGINS {0}]

proc escape_json { str } {
  return "\"[string map { \" \\\" \\ \\\\ \n \\n \r \\r \t \\t } $str]\""
}

proc json_dict { pairs } {
  set items {}
  foreach { k v } $pairs {
    if { [string is double -strict $v] } {
      lappend items "[escape_json $k]: $v"
    } else {
      lappend items "[escape_json $k]: [escape_json $v]"
    }
  }
  return "\{[join $items ", "]\}"
}

# Retarget every clock by a scale factor, before CTS. A repair-pressure
# knob on a fixed placement: synthesis and placement still reflect the
# stock period, so this is not a flow-level period sweep and is not
# reported as one.
proc rescale_clocks { scale } {
  foreach clk [sta::all_clocks] {
    set name [get_name $clk]
    # [$clk period] is in STA-internal units (seconds); create_clock
    # -period expects the user unit. Passing the raw value through creates
    # a ~zero-period clock: slack went to -954 on asap7/riscv32i and
    # repair ground for 10+ minutes on a hopeless design, which reads as a
    # slow leaf rather than a units bug. time_sta_ui is the conversion
    # Sdc.tcl itself uses in the opposite direction.
    set period [expr { [sta::time_sta_ui [$clk period]] * $scale }]
    create_clock -name $name -period $period [$clk sources]
    # Read back the clock just set: a silently-wrong constraint is
    # indistinguishable from a slow run, so make it loud instead.
    set back ""
    foreach c [sta::all_clocks] {
      if { [get_name $c] eq $name } {
        set back [sta::time_sta_ui [$c period]]
      }
    }
    if { $back eq "" || $back < 0.5 * $period || $back > 2.0 * $period } {
      error "clock rescale did not take: asked $period, read back $back"
    }
    set ::leaf_period $period
    puts "STUDY: clock $name period $period[sta::unit_scale_abbreviation time]s (scale $scale)"
  }
}

# The move's own accepted-move count, straight from repair_timing's
# summary (RSZ-109, "Replaced N buffers with inverters."). This is the
# study's inertness detector and the single most important number it
# produces: an arm that committed zero moves measured NOTHING, and any
# WNS difference it shows against another arm is noise or an unrelated
# code change. Reporting such a delta as an effect is how a null result
# gets published as a positive one.
proc committed_moves { logfile } {
  if { ![file exists $logfile] } {
    return -1
  }
  set fd [open $logfile r]
  set text [read $fd]
  close $fd
  # Match the message, not its RSZ id: the id is stable today but the
  # study should not fail silently if it is renumbered.
  if { [regexp {Replaced ([0-9]+) buffers with inverters} $text -> n] } {
    return $n
  }
  # No line at all means the move committed nothing -- repair_timing only
  # prints the summary when the count is non-zero.
  return 0
}

proc leaf_metrics { sequence margin elapsed committed } {
  set insts [[ord::get_db_block] getInsts]
  set buffers 0
  set inverters 0
  foreach inst $insts {
    set master [[$inst getMaster] getName]
    if { [string match -nocase "*BUF*" $master] } {
      incr buffers
    }
    if { [string match -nocase "*INV*" $master] } {
      incr inverters
    }
  }
  return [list \
    design $::study_design \
    arm $::study_arm \
    period_scale $::period_scale \
    clock_period $::leaf_period \
    time_unit "[sta::unit_scale_abbreviation time]s" \
    sequence $sequence \
    setup_margin $margin \
    committed_moves $committed \
    inert [expr { $committed == 0 }] \
    wns [sta::worst_slack -max] \
    tns [sta::total_negative_slack] \
    hold_wns [sta::worst_slack -min] \
    inst_count [llength $insts] \
    buffer_count $buffers \
    inverter_count $inverters \
    design_area [rsz::design_area] \
    elapsed_s $elapsed]
}

# cts.tcl and global_route.tcl write ODBs, SDCs and reports; without
# per-leaf directories every leaf clobbers every other leaf's artifacts.
# global_route_congestion_report is captured into a global when load.tcl
# is sourced, so resetting REPORTS_DIR alone is not enough.
proc isolate_leaf_io { tag } {
  set dir $::study_out/$tag
  file mkdir $dir/results $dir/reports $dir/logs
  set ::env(RESULTS_DIR) $dir/results
  set ::env(REPORTS_DIR) $dir/reports
  set ::env(LOG_DIR) $dir/logs
  set ::global_route_congestion_report $dir/reports/congestion.rpt
}

# Called from the one-line hook that patches/0050 sources in place of the
# incremental-repair call, so it runs inside global_route_helper's scope
# and $res_aware is the caller's.
#
# A single flat fork over the cross product rather than nested forks: the
# fan-out is what keeps the machine busy, and one level keeps $res_aware
# resolution simple.
proc study_grt_fork { res_aware } {
  set configs {}
  foreach sequence $::dim_sequence {
    foreach margin $::dim_margin {
      lappend configs [list $sequence $margin]
    }
  }
  puts "STUDY: [llength $configs] leaves: $configs"

  set walk_start [clock seconds]
  set statuses [fork -jobs default config $configs {
    lassign $config sequence margin
    set tag "s${sequence}_m${margin}"
    isolate_leaf_io $tag

    set ::env(SETUP_MOVE_SEQUENCE) [dict get $::sequences $sequence]
    set ::env(SETUP_SLACK_MARGIN) $margin

    # Opt-in per-move debug. The move's own debugPrint output is the only
    # direct evidence of WHY two arms agree or differ -- accepted-move
    # counts alone cannot distinguish "never considered" from "considered
    # and chose the same cell".
    if { [info exists ::env(STUDY_DEBUG_MOVE)] && $::env(STUDY_DEBUG_MOVE) ne "" } {
      set_debug_level RSZ buffer_to_inverters_move $::env(STUDY_DEBUG_MOVE)
    }

    set leaf_start [clock seconds]
    # Per-leaf log. Forked siblings share one stdout, so their output
    # interleaves arbitrarily and per-leaf facts -- the move sequence
    # actually built, the accepted-move counts -- cannot be attributed to
    # the leaf that produced them. -quiet keeps stdout for the walk's own
    # progress rather than N interleaved stage logs.
    # `tee`, not `utl::tee`: the latter is ambiguous with the C++
    # teeFileBegin/teeStringBegin helpers in the same namespace.
    #
    # The command is built with [list] so res_aware is substituted HERE,
    # by value. tee evaluates its body as `{*}$body`, which splits a
    # braced body into words WITHOUT substituting them -- passing
    # `grt_incremental_repair $res_aware` in braces handed the proc the
    # literal string "$res_aware", which reached
    # `global_route -end_incremental` as a bogus argument, failed the
    # route, and returned early. See the status check below for why that
    # was nearly invisible.
    set ok [tee -file $::study_out/$tag/logs/repair.log -quiet \
      [list grt_incremental_repair $res_aware]]

    # ORFS catches a failed global_route, writes artifacts and returns
    # rather than raising. The phase then skips repair_timing entirely and
    # the leaf still produces a complete, plausible-looking metrics
    # record -- of a design the move under test never touched. A study
    # leaf must assert that the thing it is measuring actually ran.
    if { !$ok } {
      error "grt incremental repair did not complete for $tag"
    }
    set elapsed [expr { [clock seconds] - $leaf_start }]

    set committed [committed_moves $::study_out/$tag/logs/repair.log]
    # A leaf whose sequence names the move but which committed nothing is
    # a real and reportable outcome -- on a platform whose footprint
    # filter rejects every inverter it is the EXPECTED outcome -- so this
    # is recorded, not raised. What must never happen silently is the
    # reverse: a leaf that did not name the move reporting commits.
    if { $committed > 0 && ![string match "*buffer_to_inverters*" \
      [dict get $::sequences $sequence]] } {
      error "leaf $tag committed $committed buffer_to_inverters moves with\
             a sequence that does not name the move: the per-leaf\
             SETUP_MOVE_SEQUENCE did not take"
    }
    puts "STUDY: $tag committed $committed buffer_to_inverters moves"

    set fd [open $::study_out/$tag.json w]
    puts $fd [json_dict [leaf_metrics $sequence $margin $elapsed $committed]]
    close $fd
  }]
  puts "STUDY: walk finished in [expr { [clock seconds] - $walk_start }]s"
  puts "STUDY: statuses $statuses"
}

rescale_clocks $::period_scale

# CTS and its repair are the shared prefix, so they run at stock settings:
# SETUP_MOVE_SEQUENCE is deliberately left unset here, making the post-CTS
# repair a controlled variable rather than a swept one.
source $::env(SCRIPTS_DIR)/cts.tcl

# The hook is generated rather than shipped: all the logic is above, so
# the file ORFS sources is a one-line shim, and there is no extra data
# dependency to plumb through the BUILD file.
set hook $::study_out/grt_repair_hook.tcl
set fd [open $hook w]
puts $fd "study_grt_fork \$res_aware"
close $fd
set ::env(GRT_REPAIR_HOOK_TCL) $hook

source $::env(SCRIPTS_DIR)/global_route.tcl
