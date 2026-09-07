# Second half of the round trip, for an OpenROAD that stores constraints
# in the .odb: time `read_db -sdc` on the stage output and prove fidelity
# by writing the restored constraints back out.  The caller compares the
# result with 1_synth.sdc; byte-identical means nothing was lost.
#
# Writes $RUN_OUTPUT_DIR/restore.json and $RUN_OUTPUT_DIR/restored.sdc.

source $::env(SCRIPTS_DIR)/util.tcl

proc timed { label script } {
  set t0 [sta::elapsed_run_time]
  uplevel 1 $script
  set dt [expr { [sta::elapsed_run_time] - $t0 }]
  puts [format "TIMING %-14s %8.3f s" $label $dt]
  return $dt
}

set out_dir $::env(RUN_OUTPUT_DIR)
set odb $::env(ODB_FILE)

source $::env(SCRIPTS_DIR)/read_liberty.tcl

set t_restore [timed read_db_sdc { read_db -sdc $odb }]
set t_write [timed write_sdc { write_sdc -no_timestamp $out_dir/restored.sdc }]

set fp [open $out_dir/restore.json w]
puts $fp [format "{\n  \"read_db_sdc_s\": %.3f,\n  \"write_sdc_s\": %.3f,\n  \"memory\": \"%s\"\n}" \
  $t_restore $t_write [sta::memory_usage]]
close $fp
