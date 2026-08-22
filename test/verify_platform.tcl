if {![info exists ::env(PLATFORM)] || $::env(PLATFORM) == ""} {
    puts "FAIL: PLATFORM is not set or empty!"
    exit 1
}
puts "PASS: PLATFORM is set to $::env(PLATFORM)"
exit 0
