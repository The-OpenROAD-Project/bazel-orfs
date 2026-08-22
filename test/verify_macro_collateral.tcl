if {![info exists ::env(PLATFORM)] || $::env(PLATFORM) == ""} {
    puts "FAIL: PLATFORM is not set"
    exit 1
}
if {![info exists ::env(DESIGN_NAME)] || $::env(DESIGN_NAME) == ""} {
    puts "FAIL: DESIGN_NAME is not set"
    exit 1
}
if {![info exists ::env(ADDITIONAL_LEFS)] || $::env(ADDITIONAL_LEFS) == ""} {
    puts "FAIL: ADDITIONAL_LEFS is empty or not set"
    exit 1
}
puts "PASS: Macro collateral and design immutable variables are present: PLATFORM=$::env(PLATFORM), DESIGN_NAME=$::env(DESIGN_NAME), ADDITIONAL_LEFS=$::env(ADDITIONAL_LEFS)"
exit 0
