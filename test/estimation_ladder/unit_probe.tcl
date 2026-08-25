source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file rootname [file tail $::env(ODB_FILE)]].sdc
puts "UNIT time='[sta::unit_scale_abbreviation time][sta::unit_suffix time]'"
puts "UNIT cap='[sta::unit_scale_abbreviation capacitance][sta::unit_suffix capacitance]'"
puts "UNIT res='[sta::unit_scale_abbreviation resistance][sta::unit_suffix resistance]'"
exit 0
