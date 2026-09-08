# Stage a src stage's artifacts into this run's RESULTS_DIR.
#
# RESULTS_DIR is derived from the package that declares the run, not from
# the package that built the src. Only LOG_DIR follows the src, which is
# what makes the mistake hard to see: a probe declared beside the design
# works, the same probe declared anywhere else fails with
# "ORD-0007 ... does not exist" -- which reads as a missing input rather
# than as a misconfiguration.
#
# Copying the src's files in first is what lets a probe be declared
# wherever it is useful rather than only where the design lives. Sourced
# by every probe that goes through load.tcl or open.tcl, so there is one
# copy of this reasoning rather than one per script.
#
# Extensions are best-effort except the .odb: a stage always has one, and
# the rest depend on which stage it is (.sdc from floorplan on, .spef only
# at final). A missing .odb is an error because it means the src is not a
# stage target at all.
set stage_src_odb $::env(ODB_FILE)
set stage_src_stem [file rootname $stage_src_odb]
set stage_src_results $::env(RESULTS_DIR)

if { ![file exists $stage_src_odb] } {
    error "no ODB at $stage_src_odb: the src is not a flow stage target"
}

file mkdir $stage_src_results
foreach stage_src_ext {odb sdc spef v} {
    set stage_src_from $stage_src_stem.$stage_src_ext
    set stage_src_to [file join $stage_src_results [file tail $stage_src_from]]
    if { ![file exists $stage_src_from] } {
        continue
    }
    if { [file normalize $stage_src_from] ne [file normalize $stage_src_to] } {
        file copy -force $stage_src_from $stage_src_to
    }
}

# What the probes load: the staged copy, inside RESULTS_DIR where
# load.tcl and open.tcl both look.
set stage_src_staged [file join $stage_src_results [file tail $stage_src_odb]]
