# Every pin in the design, and where its switching activity came from.
#
# `report_power -saif` never fails for want of activity. A pin the SAIF
# did not annotate is not an error: OpenSTA estimates it, and the
# estimate is good enough to look like a measurement. So an energy
# number is only as trustworthy as the account of which pins were
# measured and which were guessed.
#
# What OpenSTA does with an unannotated pin, read from the pinned
# OpenSTA (power/Power.cc) rather than assumed:
#
#   - a levelization root -- a top-level input port, or a tie cell's
#     output -- is seeded with `input_activity_`, which defaults to
#     0.1 / min_clock_period at duty 0.5. A *default*, not a measurement.
#   - anything downstream of a root gets a propagated activity: a BDD
#     evaluation of the cell's function over its inputs' densities and
#     duties. This is Najm's transition density, and it is blind to the
#     signal correlation that reconvergent fanout creates.
#   - a clock-network pin bypasses both and is given 2/period exactly,
#     from the SDC. That one is not an estimate.
#   - `PropActivityVisitor` prefers an annotated activity over a
#     propagated one for every pin it visits, so a design in which every
#     pin is annotated never propagates at all. That is the property
#     this audit exists to demonstrate.
#
# This script emits facts, not verdicts. The classification and the
# policy live in scripts/classify_pins.py, where they are unit-tested.
#
# Required env:
#   STAGE_STEM       ORFS stage stem, e.g. 5_1_grt
#   SAIF_STIMULI     path to the .saif
#   SAIF_SCOPE       hierarchy in the SAIF matching the design root
#   PINS_TSV         output: one row per pin, ODB facts
#   ANNOTATION_TXT   output: report_activity_annotation, both listings
#   DESIGN_JSON      output: clock, corner and stage facts

source $::env(SCRIPTS_DIR)/load.tcl

load_design $::env(STAGE_STEM).odb $::env(STAGE_STEM).sdc

# The same parasitics the power report uses. Activity does not depend on
# them, but running the audit against a differently-loaded design than
# the one power is reported on is exactly the kind of drift this study
# is trying to rule out.
log_cmd estimate_parasitics -global_routing

if { ![info exists ::env(SAIF_SCOPE)] || $::env(SAIF_SCOPE) eq "" } {
    error "SAIF_SCOPE is required to read the SAIF onto the linked design"
}
log_cmd read_saif -scope $::env(SAIF_SCOPE) $::env(SAIF_STIMULI)

# Both listings. The summary line above them is not load-bearing and is
# not parsed: `unannotated` is computed as pinCount() minus the size of
# the annotated map, over two pin sets that filter power/ground pins
# differently, on a size_t. The enumerations are the ground truth.
report_activity_annotation -report_annotated -report_unannotated \
    > $::env(ANNOTATION_TXT)

################################################################
# ODB facts, one row per pin.
#
# Taken from the ODB rather than from `get_pins`, because a Tcl loop
# over a hundred thousand STA pin objects costs minutes and the ODB
# carries everything the classification needs: the master's type (which
# is how a tie cell announces itself), the net's signal type (which is
# how the clock network does), and whether the pin is connected at all.

proc net_facts { net } {
    if { $net eq "NULL" || $net eq "" } {
        return [list "" "" 0]
    }
    return [list [$net getName] [$net getSigType] [$net isSpecial]]
}

# OpenSTA prints a pin as the instance path from the top plus the port,
# and for an instance inside a module that path carries the module
# prefix. odb is not consistent about whether `getName` already has it,
# so this reconstructs the prefix from the block's module instances --
# the same way power_units_grt.tcl discovers instance paths -- and
# applies it only where the name does not already start with it.
#
# Getting this wrong is not a small error. A pin whose path does not join
# reads as `unmatched` in the audit, which is a fatal verdict about a
# name mismatch rather than the correct verdict about whether the pin was
# annotated. Both mistakes are available: prefixing twice, and not
# prefixing at all.
proc hierarchical_prefixes { block } {
    set prefix [dict create]
    foreach mi [$block getModInsts] {
        set hname [$mi getHierarchicalName]
        foreach inst [[$mi getMaster] getInsts] {
            dict set prefix [$inst getName] $hname
        }
    }
    return $prefix
}

proc inst_path { inst prefix } {
    set name [$inst getName]
    if { ![dict exists $prefix $name] } {
        return $name
    }
    set hname [dict get $prefix $name]
    if { [string first "$hname/" $name] == 0 } {
        return $name
    }
    return "$hname/$name"
}

set block [ord::get_db_block]
set prefix [hierarchical_prefixes $block]
set fh [open $::env(PINS_TSV) w]
puts $fh "path\tkind\tcell\tmaster_type\tport\tdirection\tsig_type\tnet\tnet_sig_type\tnet_special"

set pin_count 0
set emitted [dict create]

foreach inst [$block getInsts] {
    set inst_name [inst_path $inst $prefix]
    dict set emitted $inst_name 1
    set master [$inst getMaster]
    set master_name [$master getName]
    set master_type [$master getType]
    foreach iterm [$inst getITerms] {
        set mterm [$iterm getMTerm]
        lassign [net_facts [$iterm getNet]] net_name net_sig net_special
        puts $fh "$inst_name/[$mterm getName]\titerm\t$master_name\t$master_type\t[$mterm getName]\t[$mterm getIoType]\t[$mterm getSigType]\t$net_name\t$net_sig\t$net_special"
        incr pin_count
    }
}

# Instances reachable only through a module instance. odb's block-level
# list has been observed to omit clock cells CTS created inside a
# module, and a pin missing from this table reads as `unmatched` -- a
# verdict about names -- rather than as unannotated, which is a verdict
# about the measurement.
foreach mi [$block getModInsts] {
    set hname [$mi getHierarchicalName]
    foreach inst [[$mi getMaster] getInsts] {
        set inst_name [inst_path $inst $prefix]
        if { [dict exists $emitted $inst_name] } {
            continue
        }
        dict set emitted $inst_name 1
        set master [$inst getMaster]
        foreach iterm [$inst getITerms] {
            set mterm [$iterm getMTerm]
            lassign [net_facts [$iterm getNet]] net_name net_sig net_special
            puts $fh "$inst_name/[$mterm getName]\titerm\t[$master getName]\t[$master getType]\t[$mterm getName]\t[$mterm getIoType]\t[$mterm getSigType]\t$net_name\t$net_sig\t$net_special"
            incr pin_count
        }
    }
}

# Top-level ports. These are the seeds of the whole propagation: an
# unannotated input port is where a default activity enters the design
# and spreads, so they are enumerated in the same table rather than
# treated as a footnote.
foreach bterm [$block getBTerms] {
    lassign [net_facts [$bterm getNet]] net_name net_sig net_special
    puts $fh "[$bterm getName]\tbterm\t\t\t[$bterm getName]\t[$bterm getIoType]\t[$bterm getSigType]\t$net_name\t$net_sig\t$net_special"
    incr pin_count
}

close $fh

################################################################
# Design facts the classification needs but the ODB does not carry: the
# clock the SDC defines, and which liberty corner was read.

proc clock_json { } {
    set out {}
    foreach clk [all_clocks] {
        set name [get_name $clk]
        set period ""
        catch { set period [get_property $clk period] }
        set sources {}
        catch {
            foreach pin [get_property $clk sources] {
                lappend sources [get_full_name $pin]
            }
        }
        set src_json {}
        foreach s $sources {
            lappend src_json "\"$s\""
        }
        lappend out "    \{\"name\": \"$name\", \"period\": \"$period\", \"sources\": \[[join $src_json ", "]\]\}"
    }
    return [join $out ",\n"]
}

proc env_or_empty { name } {
    if { [info exists ::env($name)] } {
        return $::env($name)
    }
    return ""
}

set libs {}
foreach lib [env_or_empty LIB_FILES] {
    lappend libs "\"[file tail $lib]\""
}

set fh [open $::env(DESIGN_JSON) w]
puts $fh "\{"
puts $fh "  \"stage\": \"$::env(STAGE_STEM)\","
puts $fh "  \"design\": \"[env_or_empty DESIGN_NAME]\","
puts $fh "  \"platform\": \"[env_or_empty PLATFORM]\","
puts $fh "  \"saif\": \"[file tail $::env(SAIF_STIMULI)]\","
puts $fh "  \"saif_scope\": \"$::env(SAIF_SCOPE)\","
puts $fh "  \"pin_count\": $pin_count,"
puts $fh "  \"liberty\": \[[join $libs ", "]\],"
puts $fh "  \"clocks\": \["
puts $fh "[clock_json]"
puts $fh "  \]"
puts $fh "\}"
close $fh

puts "activity_audit: $pin_count pins written to $::env(PINS_TSV)"
