# Inventory for macro_anneal.py, read off the loaded block.
#
# Everything the annealer needs and nothing it does not: the die and core
# boxes, the routing-track grids, each macro master's size and the offset
# of its lowest-layer signal pins (so an origin can be chosen that lands
# the pins on tracks), every macro instance with its hierarchical name,
# the standard-cell area under every module path (the ballast the macros
# are placed against), and how many of each macro's pins connect to
# leaf cells under each module path (the weights).
#
# Hierarchy is read from instance names. With OPENROAD_HIERARCHICAL=1 a
# kept module boundary is a `/` in the name and a flattened one a `.`,
# so the `/`-separated prefix of an instance is its path through the
# kept modules, and that is the only notion of "module" this file has.
#
# Sourced by anneal_in_flow.tcl with the floorplan initialised and the
# macros still unplaced. Plain ODB API throughout.

proc macro_anneal_module_path { inst_name } {
    set parts [split $inst_name "/"]
    if { [llength $parts] <= 1 } {
        return ""
    }
    return [join [lrange $parts 0 end-1] "/"]
}

proc dump_macro_inventory { out } {
    set block [ord::get_db_block]
    set tech [ord::get_db_tech]
    set dbu [$tech getDbUnitsPerMicron]
    set f [open $out w]

    puts $f "# macro_anneal inventory v1"
    set die [$block getDieArea]
    puts $f "die [$die xMin] [$die yMin] [$die xMax] [$die yMax] dbu $dbu"
    set core [$block getCoreArea]
    puts $f "core [$core xMin] [$core yMin] [$core xMax] [$core yMax]"
    puts $f "mfg_grid [$tech getManufacturingGrid]"
    set rows [$block getRows]
    if { [llength $rows] > 0 } {
        set site [[lindex $rows 0] getSite]
        puts $f "site [$site getWidth] [$site getHeight]"
    }

    foreach tg [$block getTrackGrids] {
        set layer [$tg getTechLayer]
        set xs [$tg getGridX]
        set ys [$tg getGridY]
        if { [llength $xs] > 1 } {
            puts $f "track [$layer getName] V [lindex $xs 0] [expr {[lindex $xs 1] - [lindex $xs 0]}]"
        }
        if { [llength $ys] > 1 } {
            puts $f "track [$layer getName] H [lindex $ys 0] [expr {[lindex $ys 1] - [lindex $ys 0]}]"
        }
    }

    # Masters: size, and the lowest-routing-level signal pin per axis.
    # A vertical-layer pin wants its x on a vertical track, a
    # horizontal-layer pin its y on a horizontal one.
    set masters {}
    set macros {}
    foreach inst [$block getInsts] {
        set master [$inst getMaster]
        if { ![$master isBlock] } { continue }
        lappend macros $inst
        set mname [$master getName]
        if { [dict exists $masters $mname] } { continue }
        set vlev 1000000; set vlayer "-"; set pox 0
        set hlev 1000000; set hlayer "-"; set poy 0
        foreach mterm [$master getMTerms] {
            if { [$mterm getSigType] ne "SIGNAL" } { continue }
            set bb [$mterm getBBox]
            set xc [expr {([$bb xMin] + [$bb xMax]) / 2}]
            set yc [expr {([$bb yMin] + [$bb yMax]) / 2}]
            foreach mpin [$mterm getMPins] {
                foreach geo [$mpin getGeometry] {
                    set layer [$geo getTechLayer]
                    set lev [$layer getRoutingLevel]
                    if { [$layer getDirection] eq "VERTICAL" } {
                        if { $lev < $vlev } { set vlev $lev; set vlayer [$layer getName]; set pox $xc }
                    } elseif { [$layer getDirection] eq "HORIZONTAL" } {
                        if { $lev < $hlev } { set hlev $lev; set hlayer [$layer getName]; set poy $yc }
                    }
                }
            }
        }
        dict set masters $mname 1
        puts $f "master $mname [$master getWidth] [$master getHeight] $vlayer $pox $hlayer $poy"
    }

    foreach inst $macros {
        puts $f "macro [$inst getName] [[$inst getMaster] getName]"
    }

    # Standard-cell area under every module path, deepest path per cell;
    # the annealer aggregates to the depth it clusters at.
    set area {}
    foreach inst [$block getInsts] {
        set master [$inst getMaster]
        if { [$master isBlock] } { continue }
        set path [macro_anneal_module_path [$inst getName]]
        set a [expr {[$master getWidth] * [$master getHeight]}]
        if { [dict exists $area $path] } {
            dict set area $path [expr {[dict get $area $path] + $a}]
        } else {
            dict set area $path $a
        }
    }
    dict for { path a } $area {
        puts $f "module [expr {$path eq "" ? "/" : $path}] $a"
    }

    # Connectivity: for each macro, how many of its pins reach leaf cells
    # (or other macros) under each module path. Macro pins are few enough
    # to walk every net they touch.
    foreach inst $macros {
        set counts {}
        foreach iterm [$inst getITerms] {
            set net [$iterm getNet]
            if { $net eq "NULL" } { continue }
            if { [$net getSigType] ne "SIGNAL" } { continue }
            foreach other [$net getITerms] {
                set oinst [$other getInst]
                if { $oinst eq $inst } { continue }
                if { [[$oinst getMaster] isBlock] } {
                    set key "macro:[$oinst getName]"
                } else {
                    set key [macro_anneal_module_path [$oinst getName]]
                    if { $key eq "" } { set key "/" }
                }
                if { [dict exists $counts $key] } {
                    dict set counts $key [expr {[dict get $counts $key] + 1}]
                } else {
                    dict set counts $key 1
                }
            }
        }
        dict for { key n } $counts {
            puts $f "net [$inst getName] $key $n"
        }
    }
    close $f
    puts "macro_anneal: inventory of [llength $macros] macros written to $out"
}
