if {$::env(PLATFORM) eq "" || $::env(DESIGN_NAME) eq "" || $::env(ADDITIONAL_LEFS) eq ""} {
    error "PLATFORM, DESIGN_NAME, and ADDITIONAL_LEFS must not be empty"
}
puts "PASS: Macro collateral and design immutable variables are present: PLATFORM=$::env(PLATFORM), DESIGN_NAME=$::env(DESIGN_NAME), ADDITIONAL_LEFS=$::env(ADDITIONAL_LEFS)"
