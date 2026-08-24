source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $::env(ODB_FILE)] [file rootname [file tail $::env(ODB_FILE)]].sdc
set blk [ord::get_db_block]
set paths [find_timing_paths -path_group reg2reg -sort_by_slack -group_path_count 1]
foreach path $paths {
    set full [get_full_name [get_property $path startpoint]]
    set idx [string last "/" $full]
    set iname [string range $full 0 [expr {$idx - 1}]]
    set tname [string range $full [expr {$idx + 1}] end]
    set esc [string map [list "\[" "\\\[" "\]" "\\\]"] $iname]
    puts "NP plain='$iname'"
    puts "NP escaped='$esc'"
    set inst [$blk findInst $esc]
    puts "NP findInst(escaped) -> $inst"
    if {$inst ne "NULL"} {
        set it [$inst findITerm $tname]
        puts "NP findITerm -> $it avgxy=[$it getAvgXY]"
        puts "NP master=[[$inst getMaster] getName] isBlock=[[$inst getMaster] isBlock]"
    }
}
exit 0
