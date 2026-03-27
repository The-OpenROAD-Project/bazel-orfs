source [file join [file dirname [info script]] util.tcl]

set_io_pin_constraint -region bottom:* -pin_names [match_pins {(R|W)[0-9]+_.*}]
