# The site grid, so the seed-sensitivity study's geometric perturbation can
# be expressed in whole sites and whole rows.
#
# Guessing these would risk the worst kind of failure: initialize_floorplan
# snaps the core rectangle to the site grid, so a nudge that is not a whole
# multiple of the site pitch can snap straight back and perturb nothing at
# all, while still looking like a perturbation in the report.
source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file rootname [file tail $::env(ODB_FILE)]].sdc
set dbu [[[ord::get_db] getTech] getDbUnitsPerMicron]
puts "SITE dbu_per_micron=$dbu"
foreach lib [[ord::get_db] getLibs] {
    foreach site [$lib getSites] {
        puts "SITE name=[$site getName]\
            width_dbu=[$site getWidth] height_dbu=[$site getHeight]\
            width_um=[expr {[$site getWidth] / double($dbu)}]\
            height_um=[expr {[$site getHeight] / double($dbu)}]"
    }
}
puts "SITE PLACE_SITE=$::env(PLACE_SITE)"
puts "SITE CORE_AREA=$::env(CORE_AREA)"
exit 0
