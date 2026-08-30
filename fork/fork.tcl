# fork.tcl -- fork/join snapshot idiom.
#
#   fork ?-parallel? ?-jobs N? ?-timeout seconds? varName valueList body
#
# For each value in valueList: fork a copy-on-write child of the whole
# process; the child sets varName in the caller's scope, evals body there,
# and _exits. Sequential by default — exactly one child alive at a time, in
# list order — because fork here is a snapshot mechanism, not parallelism:
# an in-memory checkpoint that costs nothing to take and nothing to resume.
#
# -parallel forks ALL children first, then joins. Every child is alive at
# once, so a body may rendezvous across siblings -- and so a wide value
# list oversubscribes the machine, which is what -jobs is for.
#
# -jobs N runs at most N children at a time, forking the next only as one
# is reaped: a bounded worker pool, the way a build tool schedules. This
# is what a wide fan-out wants. N defaults to $ORFS_FORK_JOBS, else the
# core count from nproc, on the reasoning that fork has already quiesced
# the host to a single thread (see below) so one child per core is one
# tool process per core.
#
# The two are mutually exclusive, and the difference is a guarantee, not a
# tuning knob: under -jobs a body must NOT wait on a sibling, because the
# sibling may not have been forked yet. That deadlocks. Rendezvous needs
# -parallel.
#
# The join is implicit: fork returns only when every child has been reaped.
# Returns a dict mapping each value to its child's exit status: 0 ok, 1 a
# Tcl error in body, N an explicit `::orfs::posix_exit N`, 128+SIG a crash
# (142 = SIGALRM: the child ran past -timeout seconds and self-destructed).
# A failed child never stops the walk — its nonzero status is recorded and
# the remaining values still run. Duplicate values are last-wins in the
# returned dict. Bodies may call fork again (nested forks walk a tree).
#
# -timeout is enforced INSIDE each child (alarm(2)), never by the parent
# killing it: an outside kill would orphan the child's own running
# descendants, which then hold the machine and the parent's stdout pipe
# open indefinitely. Deadlines do not survive fork, so a nested fork must
# pass its own -timeout for its children to stay bounded.
#
# Threads do not survive fork, and the host's persistent worker pools
# (OpenSTA's dispatch queue, sized by `-threads N` at startup) would
# deadlock the first child that dispatches to them. When the host defines
# set_thread_count/thread_count (OpenROAD does), fork quiesces the pool to
# one thread in the parent BEFORE forking -- joining live workers, which
# is fully defined -- so children run those code paths inline, and
# restores the parent's count after the join. Children must never raise
# the count themselves: that would join workers that died at fork.
# Verified, not assumed -- //test:fork_smoke probes it, and a child that
# calls set_thread_count wedges in futex_do_wait with one thread while
# its parent sits in do_wait, forever. Quiescing in the parent first does
# NOT make it safe, which was the tempting theory.
#
# The consequence is a scheduling rule worth stating, because it decides
# how long a wide walk takes. Every child is single-threaded, so:
#
#   - When the fan-out is at least the core count, this is the FASTEST
#     arrangement anyway: N single-threaded processes beat N/T processes
#     of T threads, because tool thread-scaling is sublinear while
#     process parallelism is not.
#
#   - When the fan-out is SMALLER than the core count, fork leaves the
#     machine idle -- eight children on a 64-core box use eight cores --
#     and there is no way to spend the rest from inside the walk.
#
#   - fork earns its keep through the shared prefix, so measure it before
#     reaching for it. Configurations that diverge only at a late stage
#     share almost everything; an ensemble that perturbs the floorplan
#     diverges at the root and shares only the design load, which on
#     multiplier_top is ~9s of a ~470s leaf.
#
# So: fork for a deep shared prefix, separate processes for a shallow one
# or a narrow fan-out.
# Bodies must also not run event-loop code (`vwait`, `after`-driven
# callbacks) inherited from the parent.
#
# Scripts opt in with:  source $::env(ORFS_FORK_TCL)

namespace eval ::orfs {}

if {[info commands ::orfs::posix_fork] eq ""} {
    load $::env(ORFS_FORK_LIB) Orfsfork
}

# The quiesce/restore in fork would otherwise log ORD-0030 ("Using N
# thread(s)") at every branch point.
catch {suppress_message ORD 30}

# One tool process per core, unless told otherwise. nproc honours CPU
# affinity, so a taskset-confined or cgroup-limited run gets the count it
# is actually allowed rather than the machine's.
proc ::orfs::fork_default_jobs {} {
    if {[info exists ::env(ORFS_FORK_JOBS)] && $::env(ORFS_FORK_JOBS) ne ""} {
        return $::env(ORFS_FORK_JOBS)
    }
    if {![catch {exec nproc} n] && [string is integer -strict [string trim $n]]} {
        set n [string trim $n]
        if {$n > 0} {
            return $n
        }
    }
    # Bounded rather than unbounded: guessing low costs throughput,
    # guessing high costs a thrashed machine and dishonest runtimes.
    return 4
}

proc fork {args} {
    set parallel 0
    set jobs 0
    set timeout -1
    while {[llength $args] > 3} {
        switch -- [lindex $args 0] {
            -parallel {
                set parallel 1
                set args [lrange $args 1 end]
            }
            -jobs {
                set jobs [lindex $args 1]
                set args [lrange $args 2 end]
            }
            -timeout {
                set timeout [lindex $args 1]
                set args [lrange $args 2 end]
            }
            default {
                error "fork: unknown option \"[lindex $args 0]\""
            }
        }
    }
    if {[llength $args] != 3} {
        error {usage: fork ?-parallel? ?-timeout seconds? varName valueList body}
    }
    lassign $args varName valueList body

    if {$parallel && $jobs > 0} {
        error "fork: -parallel and -jobs are mutually exclusive; -parallel\
            keeps every child alive so siblings may rendezvous, -jobs caps\
            how many run at once and so cannot guarantee that"
    }
    if {$jobs eq "default"} {
        set jobs [::orfs::fork_default_jobs]
    }
    if {$jobs > 0 && ![string is integer -strict $jobs]} {
        error "fork: -jobs must be an integer, got \"$jobs\""
    }
    # Sequential is jobs=1: reap the previous child before forking the
    # next, which is exactly the default walk. -parallel is unbounded.
    set limit [expr {$parallel ? 0 : ($jobs > 0 ? $jobs : 1)}]

    # Quiesce the host's worker pools before forking (see header). At one
    # thread, OpenSTA bypasses its dispatch queue entirely, so the dead
    # queue workers a child inherits are never touched.
    set restore_threads -1
    if {[info commands ::thread_count] ne "" &&
        [info commands ::set_thread_count] ne ""} {
        catch {
            set n [thread_count]
            if {$n > 1} {
                set_thread_count 1
                set restore_threads $n
            }
        }
    }

    set statuses [dict create]
    set pending {}
    foreach value $valueList {
        # Reap before forking, so the number alive never exceeds the
        # limit. Oldest-first: waitpid takes a specific pid, so a child
        # that finishes early is not reaped until the ones ahead of it
        # are. That costs a little throughput when durations vary and
        # keeps the bound exact, which is the property that matters.
        while {$limit > 0 && [llength $pending] / 2 >= $limit} {
            dict set statuses [lindex $pending 1] \
                [::orfs::posix_waitpid [lindex $pending 0]]
            set pending [lrange $pending 2 end]
        }
        set pid [::orfs::posix_fork]
        if {$pid == 0} {
            # Child: run body in the caller's scope, then leave via _exit —
            # returning would run the rest of the parent's script again.
            if {$timeout > 0} {
                ::orfs::posix_alarm $timeout
            }
            set rc [catch {
                uplevel 1 [list set $varName $value]
                uplevel 1 $body
            } msg opts]
            catch {
                flush stdout
                flush stderr
            }
            if {$rc == 0 || $rc == 2} {
                ::orfs::posix_exit 0
            }
            catch {
                puts stderr "fork child ($varName = $value) failed: $msg"
                puts stderr [dict get $opts -errorinfo]
                flush stderr
            }
            ::orfs::posix_exit 1
        }
        lappend pending $pid $value
    }
    foreach {pid value} $pending {
        dict set statuses $value [::orfs::posix_waitpid $pid]
    }
    if {$restore_threads > 0} {
        catch {set_thread_count $restore_threads}
    }
    return $statuses
}
