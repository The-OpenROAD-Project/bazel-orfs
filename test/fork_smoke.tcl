# fork/join smoke on real OpenROAD: a nested tree walk after load_design,
# an OpenSTA query in every leaf (exercising the thread-pool-after-fork
# hazard), one JSON per leaf in $RUN_OUTPUT_DIR, and a deliberate failing
# leaf that must not stop the walk.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

source $::env(ORFS_FORK_TCL)

set dir $::env(RUN_OUTPUT_DIR)

set statuses [fork branch {a b} {
    set inner [fork leaf {1 2} {
        if {$branch eq "b" && $leaf == 2} {
            error "deliberate failure"
        }
        # Timing queries build the graph with OpenSTA's thread pool; a
        # forked child has only one thread, so this proves the pool comes
        # back (or degrades safely) after fork.
        report_tns
        set f [open $dir/$branch$leaf.json w]
        puts $f "{\"branch\": \"$branch\", \"leaf\": $leaf}"
        close $f
    }]
    set bad 0
    dict for {_ code} $inner {
        if {$code != 0} {
            set bad 1
        }
    }
    ::orfs::posix_exit $bad
}]

# Can a child raise its own thread count?
#
# fork.tcl's header says children must never do this, on the grounds that
# it would join workers that died at fork. But fork quiesces the pool to
# one thread in the PARENT before forking, joining those workers while
# they are still alive -- so a child inherits a pool with none left to
# join, and raising the count should spawn fresh threads in the child
# rather than reap corpses.
#
# It matters because the prohibition forces every ensemble member to be
# single-threaded: a leaf on a 400um design costs ~470s that way, and a
# k=8 gate on a 64-core machine would use 8 cores and idle 56. If this
# probe deadlocks or crashes, the prohibition is right and stays; if it
# passes, fork can hand children a thread budget.
set threaded_ok 1
if {[info commands ::set_thread_count] ne ""} {
    # -timeout so the probe is fail-safe: if raising the count really does
    # try to join workers that died at fork, the child hangs, and without
    # a deadline the test would hang with it. 60s turns a deadlock into a
    # reportable status 142 instead of a wedged machine.
    set tstat [fork -timeout 60 threads {4} {
        set_thread_count $threads
        # A timing query is what actually dispatches to the pool, so it
        # is the query rather than the setter that proves the point.
        report_tns
        if {[thread_count] != $threads} {
            error "thread count did not take: [thread_count] != $threads"
        }
        ::orfs::posix_exit 0
    }]
    set tcode [dict get $tstat 4]
    if {$tcode != 0} {
        set why [expr {$tcode == 142 ? "deadlocked (timed out)" : "failed"}]
        puts stderr "child could NOT raise its thread count: $why ($tstat)"
        set threaded_ok 0
    }
}
puts "child-raises-threads: [expr {$threaded_ok ? {ok} : {UNSUPPORTED}}]"

if {$statuses ne {a 0 b 1}} {
    puts stderr "unexpected statuses: $statuses"
    exit 1
}
set got [lsort [glob -directory $dir -tails *.json]]
if {$got ne {a1.json a2.json b1.json}} {
    puts stderr "unexpected leaves: $got"
    exit 1
}
puts "fork smoke ok"
