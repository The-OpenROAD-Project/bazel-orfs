# extract.tcl for an orfs_run whose src may live in another package
# (e.g. a design in the pinned ORFS repo): load.tcl's load_design reads
# from this run's RESULTS_DIR, so stage the src's ODB/SDC there first.
set odb $::env(ODB_FILE)
set sdc [file rootname $odb].sdc
set results_odb [file join $::env(RESULTS_DIR) [file tail $odb]]
set results_sdc [file join $::env(RESULTS_DIR) [file tail $sdc]]
if { [file normalize $odb] ne [file normalize $results_odb] } {
    file mkdir $::env(RESULTS_DIR)
    file copy -force $odb $results_odb
    file copy -force $sdc $results_sdc
}
source $::env(EXTRACT_TCL)
