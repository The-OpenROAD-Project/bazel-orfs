if {[info exists ::env(GLOBAL_PLACEMENT_ARGS)] && $::env(GLOBAL_PLACEMENT_ARGS) == "-overflow 0.2"} {
    puts "Success: GLOBAL_PLACEMENT_ARGS leaked."
    exit 0
} else {
    puts "Error: GLOBAL_PLACEMENT_ARGS did not leak!"
    exit 1
}
