puts "Executable path: [info nameofexecutable]"
report_units
puts "OUTPUT=$::env(OUTPUT)"
puts "OPENROAD_EXE=$::env(OPENROAD_EXE)"
puts "OPENSTA_EXE=$::env(OPENSTA_EXE)"
set f [open $::env(OUTPUT) w]
puts $f "units"
close $f

