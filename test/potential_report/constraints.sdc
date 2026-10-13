# A period no arm meets, so every arm reports its own minimum period as
# the clock period minus its worst slack.
create_clock -name clock -period 200 [get_ports clock]
set_input_delay 0 -clock clock [delete_from_list [all_inputs] [get_ports clock]]
set_output_delay 0 -clock clock [all_outputs]
