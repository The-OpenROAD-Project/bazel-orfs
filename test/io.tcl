source test/util.tcl

set_io_pin_constraint -region left:* -pin_names [match_pins (io|auto)_.*]
