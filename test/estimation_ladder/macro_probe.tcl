# What happens to the macros when rtl_macro_placer is skipped?
source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file rootname [file tail $::env(ODB_FILE)]].sdc

initialize_floorplan -die_area $::env(DIE_AREA) -core_area $::env(CORE_AREA) -site $::env(PLACE_SITE)
if {$::env(MAKE_TRACKS) ne ""} { source $::env(MAKE_TRACKS) }
source $::env(IO_CONSTRAINTS)
place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)

proc dump_macros { tag } {
    set blk [ord::get_db_block]
    set n 0
    set placed 0
    set at_origin 0
    puts "MACROPROBE $tag ----------------"
    foreach inst [$blk getInsts] {
        set m [$inst getMaster]
        if { ![$m isBlock] } { continue }
        incr n
        set st [$inst getPlacementStatus]
        lassign [$inst getOrigin] x y
        if { $st ne "NONE" && $st ne "UNPLACED" } { incr placed }
        if { $x == 0 && $y == 0 } { incr at_origin }
        if { $n <= 6 } {
            puts "MACROPROBE $tag inst=[$inst getName] status=$st origin=[expr {$x/1000.0}],[expr {$y/1000.0}]um"
        }
    }
    puts "MACROPROBE $tag TOTAL=$n PLACED=$placed AT_ORIGIN=$at_origin"
}

dump_macros after_floorplan

if { $::env(DO_MACRO_PLACE) == 1 } {
    lassign $::env(MACRO_PLACE_HALO) hx hy
    rtl_macro_placer -halo_width $hx -halo_height $hy -target_util [place_density_with_lb_addon]
    dump_macros after_rtlmp
}

global_placement -density [place_density_with_lb_addon] -force_center_initial_place
dump_macros after_global_place

# Overlap check: do any two macros intersect?
set blk [ord::get_db_block]
set macros {}
foreach inst [$blk getInsts] {
    if { [[$inst getMaster] isBlock] } { lappend macros $inst }
}
set overlaps 0
for {set i 0} {$i < [llength $macros]} {incr i} {
    for {set j [expr {$i+1}]} {$j < [llength $macros]} {incr j} {
        set a [[lindex $macros $i] getBBox]
        set b [[lindex $macros $j] getBBox]
        if { [$a xMin] < [$b xMax] && [$b xMin] < [$a xMax] &&
             [$a yMin] < [$b yMax] && [$b yMin] < [$a yMax] } { incr overlaps }
    }
}
puts "MACROPROBE OVERLAPPING_PAIRS=$overlaps of [expr {[llength $macros]*([llength $macros]-1)/2}]"
exit 0
