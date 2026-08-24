source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file rootname [file tail $::env(ODB_FILE)]].sdc
set tech [[ord::get_db] getTech]
foreach layer [$tech getLayers] {
    if {[$layer getRoutingLevel] == 0} { continue }
    puts "LAYER [$layer getName] level=[$layer getRoutingLevel] dir=[$layer getDirection]"
}
puts "WIRE_RC_LAYER env: [expr {[info exists ::env(WIRE_RC_LAYER)] ? $::env(WIRE_RC_LAYER) : "(unset)"}]"
exit 0
