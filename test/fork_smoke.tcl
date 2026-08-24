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
