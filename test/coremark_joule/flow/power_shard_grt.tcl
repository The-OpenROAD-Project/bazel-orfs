# One shard of a hierarchical design's power: report_power on one unit's
# own global-route ODB, the SAIF read at the unit's own scope.
#
# stage_power_shards() in power.bzl runs this once for the parent and
# once for every hardened unit, and scripts/merge_power_shards.py sums
# the shards. Each unit is measured where its cells are: a hardened block
# in the parent's ODB is its abstract, pin loads and declared leakage,
# with no internal activity, so the parent alone does not measure it.
#
# What a shard writes, for each arm (vectorless, SAIF-driven):
#
#   design     report_power over the unit's own ODB, as stage_power
#              writes it
#   children   report_power -instances over the unit's children that are
#              shards of their own: the parent's blocks, or a block's
#              register files. The merge subtracts their internal and
#              leakage power; their switching power stays (see below).
#
# Which side counts a net that crosses a unit's boundary, and why the
# sum is the flat number to first order:
#
#   - OpenSTA counts a net's switching power at its driver, the
#     driver's load capacitance (its wire and every pin it loads) times
#     the driver pin's activity. A net driven by a port drives from no
#     instance, so a unit never counts its input nets.
#   - The parent's driver of a block input sees the block's pin
#     capacitance from the block's timing model, which write_timing_model
#     takes as the block's own load on that port, wire included: the
#     parent counts the whole net.
#   - A block's driver of a block output sees the block's wire and
#     loads; in the parent the same net is driven by the block's
#     instance, which loads the parent's wire and the parent's pins. So
#     each side counts its own half, and the block instance's switching
#     power in the parent is that half: it stays, and only the
#     instance's internal and leakage power (its abstract's, which the
#     block's own shard measures for real) is subtracted.
#   - What does not add up exactly: a driver's internal power depends on
#     its load and the slew at its inputs, and at a boundary each side
#     sees the other through a model (the block output driver sees the
#     SDC's load, the first cells inside a block see the SDC's input
#     slew). That is the residual of the method; the toy
#     (test/coremark_joule/power_shards, sum_test.py) measures it.
#
# The annotation rate: OpenSTA's read_saif prints how many pins it
# annotated, and report_activity_annotation counts them by origin, but
# its unannotated count subtracts across two differently filtered sets
# (activity_audit.tcl). So the annotated count is report_activity_
# annotation's `saif` line and the denominator is counted here from the
# ODB: every signal pin of every leaf instance and every signal port, the
# pins OpenSTA's own pinCount() counts.
#
# Required env:
#   STAGE_STEM          ORFS stage stem, e.g. 5_1_grt
#   SAIF_STIMULI        path to the .saif
#   SAIF_SCOPE          the unit's own scope in the SAIF: the design's
#                       scope, then the unit's instance path
#   SHARD_UNIT          the unit's instance path from the design root,
#                       empty for the parent
#   SHARD_CHILDREN      the instance paths, relative to this unit, as the
#                       ODB names them, of
#                       its children that are shards; may be empty
#   SHARD_JSON          output
#   POWER_PARASITICS    optional: global_routing (default) or placement
#   SAIF_SLASH          optional: how slash_names.py spelled `/`, __SL__
#   SHARD_UNITS_JSON    optional: per module instance, see the end

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb

# global_routing, as power_grt.tcl; placement only for the toy's proof
# of the accounting, where a flat reference's dissolved global routes
# are not the blocks' own (test/coremark_joule/power_shards)
set parasitics global_routing
if { [info exists ::env(POWER_PARASITICS)] && $::env(POWER_PARASITICS) ne "" } {
    set parasitics $::env(POWER_PARASITICS)
}
if { $parasitics ni {global_routing placement} } {
    error "power shard: POWER_PARASITICS is '$parasitics', not global_routing or placement"
}
log_cmd estimate_parasitics -$parasitics

# The voltage an abstract's output nets switch at. OpenSTA takes a
# driver's voltage from its related power pin, else from the operating
# conditions, else 0, and write_timing_model writes neither: in the
# parent a block's output pins drive the parent's wire and loads at 0 V,
# and the block's shard sees only its own half of those nets, so half of
# every block output net would be lost. The standard cells' own default
# operating conditions, the supply the block's output drivers run at,
# are set for the design; a standard cell keeps its related power pin's
# voltage, so nothing else moves. Measured on the toy
# (test/coremark_joule/power_shards): the parent halves of the block
# output nets are 0.34 mW of its 11.6 mW, and every standard-cell group
# of the parent's report is unchanged to the printed digit.
#
# Only the standard cells' libraries count: an SRAM's own library may run
# at its own voltage (CoupledL2's arrays at 0.7 V, the cells at 0.77 V),
# and the block outputs are standard-cell drivers. A library counts when
# a CORE master of the ODB has a cell in it.
set std_libs [dict create]
foreach dblib [[ord::get_db] getLibs] {
    foreach master [$dblib getMasters] {
        if { [string match CORE* [$master getType]] } {
            foreach lc [get_lib_cells -quiet [$master getName]] {
                dict set std_libs [get_name [get_property $lc library]] 1
            }
        }
    }
}
set op_conds {}
foreach lib [get_libs *] {
    if { ![dict exists $std_libs [get_name $lib]] } {
        continue
    }
    set oc [$lib default_operating_conditions]
    if { $oc ne "NULL" } {
        lappend op_conds [list [get_name $lib] $oc [$oc voltage]]
    }
}
if { [llength $op_conds] == 0 } {
    error "power shard: no standard-cell library has default operating conditions to take the supply voltage from"
}
foreach c $op_conds {
    if { [lindex $c 2] != [lindex [lindex $op_conds 0] 2] } {
        error "power shard: the standard-cell libraries' operating voltages differ ([lindex $c 0] [lindex $c 2] V, [lindex [lindex $op_conds 0] 0] [lindex [lindex $op_conds 0] 2] V); which one an abstract's outputs switch at is not decided"
    }
}
sta::set_operating_conditions_cmd [lindex [lindex $op_conds 0] 1] all
puts "power shard: operating conditions of [lindex [lindex $op_conds 0] 0], [lindex [lindex $op_conds 0] 2] V"

# More digits than report_power's default: the merge sums and
# subtracts, and a sum is compared with a flat report.
set digits 6

# A cell's name can hold `/` where hierarchy was flattened into it: in a
# flat ODB every cell of a hierarchically synthesised unit,
# `u_core/lane[0].u_lane/_060_`, and in a hierarchical one any cell or
# macro below a module that was not kept, `inner_ftq/entryQueue`. A
# SAIF cannot carry a `/` in a name. grt_netlist(saif_names = True)
# spells it as SAIF_SLASH in the simulated netlist
# (scripts/slash_names.py), and the same is done here to the part of
# each instance's name below its module instance, so the SAIF's names
# are the ODB's. A module instance's own name with a `/` is not handled
# and stops the run.
set slash __SL__
if { [info exists ::env(SAIF_SLASH)] && $::env(SAIF_SLASH) ne "" } {
    set slash $::env(SAIF_SLASH)
}
set block [ord::get_db_block]
# read flat (OPENROAD_HIERARCHICAL=0), the ODB may still hold the
# synthesis's module instances, but the timer and write_verilog see one
# module
set hier [[ord::get_db] hasHierarchy]
set top_module [$block getTopModule]
if { $hier } {
    foreach mi [$block getModInsts] {
        if { [string first / [$mi getName]] >= 0 } {
            error "power shard: module instance [$mi getHierarchicalName] has a `/` in its own name; a SAIF scope cannot hold it"
        }
    }
}
proc module_prefix { inst } {
    if { !$::hier } {
        return ""
    }
    set m [$inst getModule]
    if { $m eq "NULL" || $m eq $::top_module } {
        return ""
    }
    return "[[$m getModInst] getHierarchicalName]/"
}
proc saif_name { inst } {
    set n [$inst getName]
    set prefix [module_prefix $inst]
    if { $prefix ne "" && [string first $prefix $n] != 0 } {
        # a cell placed in a module instance under a name of its own, not
        # the instance's path (CTS's clkbuf_leaf_3_inner_ptw/ptw.cache/_ckg_Q
        # in MemBlock's inner_ptw/ptw.cache): write_verilog writes the
        # whole name in that module, slash_names spells its every `/`
        return "$prefix[string map [list / $::slash] $n]"
    }
    return "$prefix[string map [list / $::slash] [string range $n [string length $prefix] end]]"
}

# The children, found by the path given before anything is renamed, and
# where the SAIF has each: the merge checks that a child's shard read
# the SAIF there. A child that is not an instance of this unit would
# subtract nothing and count its block twice; stop instead.
set child_insts {}
set child_scopes {}
set missing {}
if { [info exists ::env(SHARD_CHILDREN)] } {
    foreach child $::env(SHARD_CHILDREN) {
        set inst [$block findInst $child]
        if { $inst eq "NULL" } {
            lappend missing $child
            continue
        }
        lappend child_insts $inst
        lappend child_scopes [saif_name $inst]
    }
}
if { [llength $missing] > 0 } {
    error "power shard [string trim $::env(SHARD_UNIT)]: no instance [join $missing {, }] in [$block getName]; a shard's path names the instance of its block in this unit"
}

set renamed 0
foreach inst [$block getInsts] {
    set n [$inst getName]
    if { [string first $slash $n] >= 0 } {
        error "power shard: instance $n already holds $slash; the rename would not be reversible"
    }
    set to [saif_name $inst]
    if { $to ne $n } {
        $inst rename $to
        incr renamed
    }
}
puts "power shard: [expr { $hier ? {hierarchical} : {flat} }] ODB, $renamed instance names spelled with $slash"
set children {}
foreach inst $child_insts {
    lappend children [$inst getName]
}

set tmp_dir [file dirname $::env(SHARD_JSON)]

proc capture { tag args } {
    set f [file join $::tmp_dir "power_shard_$tag.txt"]
    {*}$args > $f
    set fh [open $f r]
    set body [string trim [read $fh]]
    close $fh
    file delete -force $f
    return $body
}

proc arm { tag } {
    set design [capture "${tag}_design" report_power -format json -digits $::digits]
    if { [llength $::children] > 0 } {
        # report_power writes an instance's name as it is, an escaped
        # bus bit's backslash included, which JSON reads as an escape
        set kids [string map {\\ \\\\} [capture "${tag}_children" report_power \
            -format json -digits $::digits -instances [get_cells $::children]]]
    } else {
        set kids {[]}
    }
    return "\{\"design\": $design, \"children\": $kids\}"
}

log_cmd report_power
set vectorless [arm vectorless]

log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)
set annotation [capture annotation report_activity_annotation]
puts $annotation
set saif_pins 0
foreach line [split $annotation "\n"] {
    if { [regexp {^saif\s+([0-9]+)} [string trim $line] -> n] } {
        set saif_pins $n
    }
}

log_cmd report_power
set vector_driven [arm vector_driven]

# The denominator, OpenSTA's pinCount() from the ODB: signal pins of
# leaf instances, and the ports.
set pins 0
foreach inst [$block getInsts] {
    foreach iterm [$inst getITerms] {
        set type [$iterm getSigType]
        if { $type ne "POWER" && $type ne "GROUND" } {
            incr pins
        }
    }
}
foreach bterm [$block getBTerms] {
    set type [$bterm getSigType]
    if { $type ne "POWER" && $type ne "GROUND" } {
        incr pins
    }
}
puts "power shard: $saif_pins of $pins pins annotated from the SAIF at $::env(SAIF_SCOPE)"

proc json_string { s } {
    return "\"[string map {\\ \\\\ \" \\\"} $s]\""
}
set child_list {}
if { [info exists ::env(SHARD_CHILDREN)] } {
    foreach child $::env(SHARD_CHILDREN) {
        lappend child_list [json_string $child]
    }
}
set name_list {}
foreach child $children {
    lappend name_list [json_string $child]
}
set scope_list {}
foreach scope $child_scopes {
    lappend scope_list [json_string $scope]
}

set out [open $::env(SHARD_JSON) w]
puts $out "\{"
puts $out "  \"unit\": [json_string $::env(SHARD_UNIT)],"
puts $out "  \"design\": [json_string [$block getName]],"
puts $out "  \"scope\": [json_string $::env(SAIF_SCOPE)],"
puts $out "  \"children\": \[[join $child_list {, }]\],"
puts $out "  \"child_names\": \[[join $name_list {, }]\],"
puts $out "  \"child_scopes\": \[[join $scope_list {, }]\],"
puts $out "  \"annotation\": \{\"saif_pins\": $saif_pins, \"pins\": $pins\},"
puts $out "  \"vectorless\": $vectorless,"
puts $out "  \"vector_driven\": $vector_driven"
puts $out "\}"
close $out

# Per module (optional, SHARD_UNITS_JSON): the SAIF-driven power of every
# module instance the unit's ODB keeps, as power_units_grt.tcl reports it
# for one design, here on the unit's own ODB and SAIF. One row per module
# instance: its path below the unit, its depth (1: a module instance of
# the unit's top), its module, and report_power -instances on it, a
# hierarchical instance's power being its leaf cells'. A child that is a
# shard of its own sits where it sits; its abstract's internal and
# leakage power are taken out of every row it is under, as the sum takes
# them out of the unit (only its switching, the nets it drives here,
# stays), so no power is counted in two shards. The unit's own flat
# remainder, the cells under no module instance, is the merge's to
# compute: the shard's total less its depth-1 rows.
if { [info exists ::env(SHARD_UNITS_JSON)] && $::env(SHARD_UNITS_JSON) ne "" } {
    set child_power {}
    if { [llength $children] > 0 } {
        set rows [capture units_children report_power -format json -digits $::digits \
            -instances [get_cells $children]]
        # name -> internal + leakage, from report_power's own JSON rows
        foreach {- name internal leakage} [regexp -all -inline \
            {"name": "([^"]*)",\s*"internal": ([-0-9.eE+]+),\s*"switching": [-0-9.eE+]+,\s*"leakage": ([-0-9.eE+]+)} $rows] {
            dict set child_power [string map {\\ ""} $name] [list $internal $leakage]
        }
    }
    set out [open $::env(SHARD_UNITS_JSON) w]
    puts $out "\["
    set first 1
    set count 0
    foreach mi [$block getModInsts] {
        set path [$mi getHierarchicalName]
        if { [get_cells -quiet $path] eq {} } {
            continue
        }
        set depth [llength [split $path /]]
        set row [capture unit_row report_power -format json -digits $::digits -instances [get_cells $path]]
        regexp {"internal": ([-0-9.eE+]+)} $row - internal
        regexp {"switching": ([-0-9.eE+]+)} $row - switching
        regexp {"leakage": ([-0-9.eE+]+)} $row - leakage
        dict for {child pl} $child_power {
            if { [string first "$path/" $child] == 0 } {
                set internal [expr { $internal - [lindex $pl 0] }]
                set leakage [expr { $leakage - [lindex $pl 1] }]
            }
        }
        if { !$first } { puts $out "," }
        set first 0
        puts -nonewline $out [format \
            "  \{\"path\": %s, \"module\": %s, \"depth\": %d, \"internal\": %.6e, \"switching\": %.6e, \"leakage\": %.6e\}" \
            [json_string $path] [json_string [[$mi getMaster] getName]] $depth $internal $switching $leakage]
        incr count
    }
    puts $out "\n\]"
    close $out
    puts "power shard: $count module instances reported"
}
