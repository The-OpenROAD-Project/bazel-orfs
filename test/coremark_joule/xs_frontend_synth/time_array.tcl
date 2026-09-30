# openroad -exit time_array.tcl: a structured_gen array timed on its own
# placed gates, read address to read data. Environment: XS_LIBS and
# XS_SETRC as load.tcl, RF_ODB the generator's --odb, RF_OUT the result
# line; the path goes beside it as <RF_OUT without extension>_read.txt.
foreach f [glob $::env(XS_LIBS)/asap7sc7p5t_*.lib] { read_liberty $f }
read_db $::env(RF_ODB)
source $::env(XS_SETRC)
create_clock -name clk -period 473 [get_ports clock]
set_input_transition 10 [all_inputs]
set_load 1 [all_outputs]
set ins [get_ports io_readPorts_0_addr*]
set outs [get_ports io_readPorts_0_data*]
set_max_delay 473 -from $ins -to $outs
estimate_parasitics -placement
set p [find_timing_paths -from $ins -to $outs -path_delay max -group_path_count 1]
set f [open $::env(RF_OUT) w]
puts $f "read addr->data (placement parasitics): [sta::format_time [[lindex $p 0] data_arrival_time] 1] ps"
close $f
report_checks -from $ins -to $outs -path_delay max -fields {slew cap fanout} -digits 1 \
  > [file rootname $::env(RF_OUT)]_read.txt
