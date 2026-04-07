source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb 1_synth.sdc

set block [ord::get_db_block]
set num_cells [llength [$block getInsts]]

if {$num_cells < 500} {
    set util 50
} elseif {$num_cells < 5000} {
    set util 40
} else {
    set util 30
}
set density [format "%.2f" [expr {$util / 100.0 + 0.15}]]

set out [file join $::env(WORK_HOME) $::env(OUTPUT)]
set f [open $out w]
puts $f "\{\"CORE_UTILIZATION\": \"$util\", \"PLACE_DENSITY\": \"$density\"\}"
close $f

puts "Cell count: $num_cells"
puts "Computed CORE_UTILIZATION=$util PLACE_DENSITY=$density"
