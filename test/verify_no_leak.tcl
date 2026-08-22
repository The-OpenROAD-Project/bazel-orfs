if {[info exists ::env(GLOBAL_PLACEMENT_ARGS)] && $::env(GLOBAL_PLACEMENT_ARGS) == "-overflow 0.2"} {
    puts "Error: GLOBAL_PLACEMENT_ARGS leaked! Value is $::env(GLOBAL_PLACEMENT_ARGS)"
    exit 1
} else {
    puts "Success: GLOBAL_PLACEMENT_ARGS did not leak."
    exit 0
}
