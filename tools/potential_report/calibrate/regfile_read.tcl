# A generated register file's read path, timed on its own placement:
# generate_regfile builds the block into the database, placement
# parasitics come from the platform's layer RC, and the read is the
# worst path to a read-data port with no I/O delay. Timed twice: as
# generated (no buffer anywhere, so a long wordline's slew is whatever
# its decode gate makes of it) and after the flow's own repair_design
# and repair_timing against a period no read meets, the way the flow
# meets the block. Prints one line:
#   raw_read_ps <a> buffered_read_ps <a> read_ps <a> write_ps <a> buffers <n>
#   openroad regfile_read.tcl  (env: TECH_LEF CELL_LEF LIB_FILES SET_RC SPEC)
read_lef $::env(TECH_LEF)
read_lef $::env(CELL_LEF)
foreach lib $::env(LIB_FILES) {
  read_liberty $lib
}
generate_regfile -spec $::env(SPEC)
source $::env(SET_RC)
set period 100
create_clock -name clk -period $period [get_ports clock]
set inputs [delete_from_list [all_inputs] [get_ports clock]]
set_input_delay 0 -clock clk $inputs
set_output_delay 0 -clock clk [all_outputs]
set_driving_cell -lib_cell BUFx4_ASAP7_75t_R $inputs
estimate_parasitics -placement
proc worst_arrival { period to } {
  set paths [find_timing_paths -path_delay max -to $to -group_path_count 1]
  if { [llength $paths] == 0 } {
    return -1
  }
  # Arrival from slack: required is the period, less the setup time at
  # a register (a few ps, ignored). The clock is ideal.
  return [expr { $period - [get_property [lindex $paths 0] slack] }]
}
set raw [worst_arrival $period [all_outputs]]
set before [llength [get_cells *]]
repair_design
estimate_parasitics -placement
set buffered [worst_arrival $period [all_outputs]]
# Bounded: against a period no read meets, an unbounded repair_timing
# grinds for as long as it finds anything to try.
repair_timing -setup -skip_pin_swap -max_iterations 2000
estimate_parasitics -placement
set rd [worst_arrival $period [all_outputs]]
set wr [worst_arrival $period [all_registers -data_pins]]
puts [format "raw_read_ps %.1f buffered_read_ps %.1f read_ps %.1f write_ps %.1f buffers %d" \
  $raw $buffered $rd $wr [expr { [llength [get_cells *]] - $before }]]
