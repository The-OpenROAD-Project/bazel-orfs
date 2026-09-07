# Time the constraint round trip on a synthesized design.
#
# Runs as an orfs_run script against a *_synth stage: RESULTS_DIR holds
# 1_synth.odb and 1_synth.sdc.  Reads the liberty the way ORFS does, then
# times each step the flow pays at every stage boundary:
#
#   read_db            the design (baseline the constraints ride on)
#   read_sdc           the generated 1_synth.sdc (what every substep pays)
#   write_sdc          what every stage pays on the way out
#   write_db           the design (with the patch: constraints included)
#   read_db -sdc       (patched OpenROAD only) constraints restored from
#                      the .odb, in a second process -- see sdc_restore.tcl
#
# Writes $RUN_OUTPUT_DIR/timing.json with seconds per step, plus the sizes
# of the files involved, so the numbers can be tabulated across designs
# and binaries.  Uses OpenSTA's wall clock (sta::elapsed_run_time) so the
# script does not depend on Tcl's clock package being on the library path.

source $::env(SCRIPTS_DIR)/util.tcl

proc timed { label script } {
  set t0 [sta::elapsed_run_time]
  uplevel 1 $script
  set dt [expr { [sta::elapsed_run_time] - $t0 }]
  puts [format "TIMING %-14s %8.3f s" $label $dt]
  return $dt
}

# The src stage's results are staged in its own variant folder (which is
# not RESULTS_DIR when the design lives in another package); its .odb is
# exposed as ODB_FILE and 1_synth.sdc sits next to it.
set out_dir $::env(RUN_OUTPUT_DIR)
set odb $::env(ODB_FILE)
set sdc [file join [file dirname $odb] 1_synth.sdc]

source $::env(SCRIPTS_DIR)/read_liberty.tcl

set t(read_db) [timed read_db { read_db $odb }]
set t(read_sdc) [timed read_sdc { read_sdc $sdc }]
set t(write_sdc) [timed write_sdc { write_sdc -no_timestamp $out_dir/roundtrip.sdc }]
set t(write_db) [timed write_db { write_db $out_dir/roundtrip.odb }]

set fp [open $out_dir/timing.json w]
puts $fp "{"
puts $fp "  \"registers\": [llength [all_registers]],"
puts $fp "  \"ports\": [llength [get_ports *]],"
puts $fp "  \"sdc_bytes\": [file size $sdc],"
puts $fp "  \"odb_bytes\": [file size $odb],"
puts $fp "  \"roundtrip_odb_bytes\": [file size $out_dir/roundtrip.odb],"
foreach k {read_db read_sdc write_sdc write_db} {
  puts $fp [format "  \"%s_s\": %.3f," $k $t($k)]
}
# Peak resident set size of this process, as OpenSTA reports it.
puts $fp "  \"memory\": \"[sta::memory_usage]\""
puts $fp "}"
close $fp
