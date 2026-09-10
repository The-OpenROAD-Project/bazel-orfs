# STA and rsz must produce the same design at any thread count.
#
# This is the regression bazel-orfs#970 says was missing every time the
# fence went up and came down. Thread-count non-idempotency in OpenSTA
# has been found and fixed at least four times -- ORFS#3046 (a per-vertex
# path index keyed by `Tag*`), ORFS#3180 (a crash only with threads),
# OpenROAD#9781 (repair_timing's hash differing run to run at 16 threads
# and identical at 1), and the Feb-2026 fork that forced STA to one
# thread "until issues resolved" -- every time by a flow user diffing
# outputs, never by a test. OpenROAD's regressions run single-threaded;
# gpl has `mt_invariance01`, STA has nothing.
#
# Deliberately shaped like `src/gpl/test/mt_invariance01.tcl`: run the
# thing at a thread count, write the result, diff it against the
# single-threaded golden. Here the golden is the sibling arm of this
# same script rather than a checked-in `.ok` file, so the pair cannot
# drift apart when the design or the tool changes -- both arms move
# together and only the *difference* between them is asserted.
#
# `repair_timing` is the payload and not `report_checks`, because a
# reporting difference is cosmetic while a repair difference is a
# different netlist: rsz asks STA which paths are critical, and a
# divergent answer inserts different buffers. That is the OpenROAD#9781
# shape exactly.

source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc

set threads $::env(MT_THREADS)
set_thread_count $threads

# The knob has to be witnessed, not assumed -- and asserted here rather
# than diffed. `set_thread_count` clamps to
# std::thread::hardware_concurrency() and logs the clamped value, so on
# a machine with fewer hardware threads than the arm asks for, both arms
# would run at the same count and the test would pass by measuring
# nothing. That is the failure mode this whole test exists to avoid, so
# it is a hard error in the arm.
#
# It cannot be a line in the report instead: the two arms are supposed
# to disagree about their thread count and to agree about everything
# else, so a thread count in the diffed file would fail the test every
# time it worked.
set installed [thread_count]
if { $installed != $threads } {
  utl::error ORD 9970 "asked for $threads thread(s), OpenROAD installed\
    $installed: this host cannot run the arm, and two arms at the same\
    thread count would pass this test while measuring nothing."
}

# Parasitics first, so repair_timing has the same starting estimate in
# both arms. Without this the arms could differ because one of them
# repaired against stale parasitics.
estimate_parasitics -placement

repair_timing

# What a divergence moves, in the order it is worth reading. Numbers
# rather than a full report: a `report_checks` dump carries path names
# whose order is itself the thing under test, so a diff of it cannot
# distinguish "different timing" from "same timing, different order".
set block [ord::get_db_block]
set insts [llength [$block getInsts]]
set nets [llength [$block getNets]]

# Only comparable numbers go in the file. The thread count does not,
# for the reason above.
set fd [open $::env(MT_REPORT) w]
puts $fd "worst_slack_max [sta::worst_slack -max]"
puts $fd "worst_slack_min [sta::worst_slack -min]"
puts $fd "total_negative_slack [sta::total_negative_slack]"
puts $fd "instances $insts"
puts $fd "nets $nets"
close $fd

# The strong statement. A metric report can agree while the netlist
# differs, so the post-repair design is written and byte-compared too --
# the same claim `gcd_single_flow` makes at all seven stage boundaries,
# with the same comparator.
write_db $::env(MT_ODB)
