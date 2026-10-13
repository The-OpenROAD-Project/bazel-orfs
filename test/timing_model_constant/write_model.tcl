# Write blk's timing model to $::env(MODEL).
foreach lef $::env(LEFS) {
  read_lef $lef
}
foreach lib $::env(LIBS) {
  read_liberty $lib
}
read_verilog [file join [file dirname [info script]] blk.v]
link_design blk
create_clock -name clk -period 1000 [get_ports clk]
set_input_delay 0 -clock clk [get_ports d]
set_output_delay 0 -clock clk [get_ports {q z0 z1 zand}]
write_timing_model $::env(MODEL)
