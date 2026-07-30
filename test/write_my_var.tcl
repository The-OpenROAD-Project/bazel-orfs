set f [open $::env(OUTPUT) w]
if {[info exists ::env(MY_CUSTOM_VAR)]} {
    puts $f "MY_CUSTOM_VAR is $::env(MY_CUSTOM_VAR)"
} else {
    puts $f "MY_CUSTOM_VAR is MISSING"
}
close $f
