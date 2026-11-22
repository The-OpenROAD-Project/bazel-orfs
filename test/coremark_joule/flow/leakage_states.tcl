# Every leaf cell's leakage as report_power has it after a power shard's
# SAIF-driven arm, with the duty of each of its signal pins: the input
# to scripts/leakage_states.py, which recomputes each cell's leakage
# from its liberty `when` states with an output pin taken as the
# function of the inputs (OpenSTA weights a `when` that names an output
# as if the output were independent of the inputs).
#
# Runs power_shard_grt.tcl first, with its env (power_shard()'s), then
# writes LEAKAGE_STATES_TSV: one line per library (`lib <file>`), then
# one per leaf instance, `<cell> <leakage W> <pin>=<duty> ...`.

source $::env(LEAKAGE_SHARD_TCL)

set out [open $::env(LEAKAGE_STATES_TSV) w]
foreach lib [get_libs *] {
    puts $out "lib [file tail [get_property $lib filename]]"
}
set scene [sta::cmd_scene]
set n 0
foreach inst [get_cells -hierarchical *] {
    if { [get_property $inst is_hierarchical] } {
        continue
    }
    set line "[get_property $inst ref_name] [lindex [sta::instance_power $inst $scene] 2]"
    foreach pin [get_pins -of_objects $inst] {
        set activity [get_property $pin activity]
        append line " [get_property $pin lib_pin_name]=[lindex $activity 1]"
    }
    puts $out $line
    incr n
}
close $out
puts "leakage states: $n leaf instances"
