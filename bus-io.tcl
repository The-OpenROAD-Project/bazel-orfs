source util.tcl

set_io_pin_constraint -region left:* -pin_names {in clock}
set_io_pin_constraint -region right:* -pin_names [match_pins out.*]
