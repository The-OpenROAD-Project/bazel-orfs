# Extract DRC marker locations and types from routed ODB.
#
# Iterates over dbMarkerCategory hierarchy, prints each violation
# with its bounding box and type. Output is CSV-like for easy
# parsing by a Python plotting script.
#
# Run via: tmp/.../make run RUN_SCRIPT=$(pwd)/gemmini_8x8_abutted/drc_locations.tcl

source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_2_route.odb 5_1_grt.sdc

set block [ord::get_db_block]
set dbu [ord::dbu_to_microns 1]

puts "# DRC violations from routed ODB"
puts "# type,xlo_um,ylo_um,xhi_um,yhi_um,layer"

set total 0
foreach cat [$block getMarkerCategories] {
    set tool_name [$cat getName]
    foreach subcat [$cat getMarkerCategories] {
        set viol_type [$subcat getName]
        foreach marker [$subcat getMarkers] {
            set bbox [$marker getBBox]
            set xlo [expr {[$bbox xMin] * $dbu}]
            set ylo [expr {[$bbox yMin] * $dbu}]
            set xhi [expr {[$bbox xMax] * $dbu}]
            set yhi [expr {[$bbox yMax] * $dbu}]

            # Try to get layer
            set layer_name "unknown"
            catch {
                set tech_layer [$marker getTechLayer]
                if {$tech_layer ne "NULL"} {
                    set layer_name [$tech_layer getName]
                }
            }

            puts "$viol_type,$xlo,$ylo,$xhi,$yhi,$layer_name"
            incr total
        }
    }
}

puts "# Total: $total violations"
