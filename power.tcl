source $::env(SCRIPTS_DIR)/open.tcl

set f [open $::env(OUTPUT) a]
puts $f "name: $::env(DESIGN_NAME)"
puts $f "instances: [llength [get_cells *]]"
puts $f "area: [sta::format_area [rsz::design_area] 0]"

set_power_activity -input -activity 0.5

report_power > tmp.txt
exec cat tmp.txt
set f2 [open tmp.txt r]
set power_line [lindex [split [read $f2] "\n"] 9]
regexp {(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)} $power_line -> _ _ _ _ power
close $f2

report_clock_min_period
set clock_period_ps [sta::find_clk_min_period [lindex [all_clocks] 0] 0]

puts $f "power: $power"
puts $f "clock_period: $clock_period_ps"
close $f
