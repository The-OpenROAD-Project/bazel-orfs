source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_2_floorplan_macro.odb 2_1_floorplan.sdc

set f [file join $::env(WORK_HOME) "macro_placement.tcl"]

puts "Message is: $::env(MESSAGE)"

write_macro_placement $f

set f [open $f r]
set content [read $f]
set content [string map {"/" "."} $content]
close $f

set f [open $f w]
puts -nonewline $f $content
close $f
