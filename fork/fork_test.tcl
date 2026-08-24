# Unit tests for the fork/join idiom in fork.tcl, run in plain tclsh —
# the idiom is host-agnostic, so everything except OpenROAD-specific
# hazards (thread pools) is testable here in milliseconds.

source $::env(ORFS_FORK_TCL)

set dir $::env(TEST_TMPDIR)
set failures 0

proc check {label expected actual} {
    if {$expected eq $actual} {
        puts "ok: $label"
        return
    }
    puts stderr "FAIL: $label\n  expected: $expected\n  actual:   $actual"
    incr ::failures
}

# 1. All children succeed: dict of zeros, side effects present.
set st [fork x {a b c} {
    set f [open $dir/ok.$x w]
    puts $f $x
    close $f
}]
check "all-ok statuses" {a 0 b 0 c 0} $st
check "all-ok side effects" {ok.a ok.b ok.c} \
    [lsort [glob -directory $dir -tails ok.*]]

# 2. Sequential by default: each child sees exactly the files its
# predecessors wrote, so the recorded counts must be 0, 1, 2.
set st [fork x {p q r} {
    set n [llength [glob -nocomplain -directory $dir seq.*]]
    set f [open $dir/seq.$x w]
    puts $f $n
    close $f
}]
check "sequential statuses" {p 0 q 0 r 0} $st
set counts {}
foreach x {p q r} {
    set f [open $dir/seq.$x r]
    lappend counts [string trim [read $f]]
    close $f
}
check "sequential ordering" {0 1 2} $counts

# 3. A Tcl error in one body is status 1; the walk continues.
set st [fork x {a bad c} {
    if {$x eq "bad"} {
        error boom
    }
    close [open $dir/walk.$x w]
}]
check "error status recorded" {a 0 bad 1 c 0} $st
check "walk continued past failure" {walk.a walk.c} \
    [lsort [glob -directory $dir -tails walk.*]]

# 4. Explicit exit codes propagate.
set st [fork x {u v} {
    if {$x eq "v"} {
        ::orfs::posix_exit 42
    }
}]
check "explicit exit code" {u 0 v 42} $st

# 5. A crashed child (signal) is 128+SIG; siblings unaffected.
set st [fork x {fine crash} {
    if {$x eq "crash"} {
        exec kill -KILL [pid]
    }
}]
check "signal status" {fine 0 crash 137} $st

# 6. Nested forks: the inner dict is visible to the forking child, which
# forwards failure by exiting nonzero iff any inner status is nonzero.
set st [fork outer {L R} {
    set inner [fork n {1 2} {
        if {$outer eq "R" && $n == 2} {
            error boom
        }
        close [open $dir/leaf.$outer.$n w]
    }]
    set bad 0
    dict for {_ code} $inner {
        if {$code != 0} {
            set bad 1
        }
    }
    ::orfs::posix_exit $bad
}]
check "nested statuses" {L 0 R 1} $st
check "nested leaves" {leaf.L.1 leaf.L.2 leaf.R.1} \
    [lsort [glob -directory $dir -tails leaf.*]]

# 7. Isolation: a child's writes never reach the parent.
set shared parent
set st [fork x {only} {
    set ::shared child
}]
check "child isolated from parent" parent $shared
check "isolation status" {only 0} $st

# 8. -timeout: an overrunning child self-destructs via its own alarm
# (128+SIGALRM = 142); siblings before and after are unaffected.
# (clock is unavailable in the hermetic tclsh, so the wall guard uses date.)
set t0 [exec date +%s]
set st [fork -timeout 1 x {quick stuck also_quick} {
    if {$x eq "stuck"} {
        after 30000
    }
}]
set elapsed [expr {[exec date +%s] - $t0}]
check "timeout status" {quick 0 stuck 142 also_quick 0} $st
if {$elapsed > 10} {
    puts stderr "FAIL: timeout did not cut the stuck child short (${elapsed}s)"
    incr ::failures
}

# 9. -parallel is a real barrier: every child blocks until all three have
# announced themselves, which can only complete if all were forked before
# the join. A sequential walk would time out (status 1).
set st [fork -parallel x {1 2 3} {
    close [open $dir/par.$x w]
    for {set i 0} {$i < 1000} {incr i} {
        if {[llength [glob -nocomplain -directory $dir par.*]] == 3} {
            ::orfs::posix_exit 0
        }
        after 10
    }
    ::orfs::posix_exit 1
}]
check "parallel barrier" {1 0 2 0 3 0} $st

if {$failures > 0} {
    puts stderr "$failures test(s) failed"
    exit 1
}
puts "all fork tests passed"
