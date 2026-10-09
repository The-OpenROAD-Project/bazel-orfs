# Every register of a stage's ODB and how many of them STA sees clocked,
# as JSON for check_clocked.py. A register that STA does not see clocked
# is no timing endpoint or startpoint: placement and repair cannot see the
# paths through it.
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)
set registers [all_registers -cells]
set clocked [all_registers -cells -clock [all_clocks]]
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"registers\": [llength $registers],"
puts $out "  \"clocked\": [llength $clocked]"
puts $out "}"
close $out
