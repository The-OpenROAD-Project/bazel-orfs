# What CTS added to the parent, read from its own log: the clock buffers of
# every tree, the delay buffers that balance the macros' insertion delay,
# the dummy loads. Kept to pure Tcl so it needs no design loaded.
set log [file join $::env(LOG_DIR) 4_1_cts.log]
set fp [open $log r]
set text [read $fp]
close $fp
set clock_buffers 0
foreach {- n} [regexp -all -inline {Created (\d+) clock buffers} $text] { incr clock_buffers $n }
set delay_buffers 0
foreach {- n} [regexp -all -inline {Total number of delay buffers: (\d+)} $text] { incr delay_buffers $n }
set dummy_loads 0
foreach {- n} [regexp -all -inline {Dummy loads inserted (\d+)} $text] { incr dummy_loads $n }
set macro_sinks 0
regexp {for macros has (\d+) sinks} $text - macro_sinks
set args ""
regexp -line {^clock_tree_synthesis (.*)$} $text - args
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"cts_args\": \"$args\","
puts $out "  \"macro_sinks\": $macro_sinks,"
puts $out "  \"clock_buffers\": $clock_buffers,"
puts $out "  \"delay_buffers\": $delay_buffers,"
puts $out "  \"dummy_loads\": $dummy_loads"
puts $out "}"
close $out
