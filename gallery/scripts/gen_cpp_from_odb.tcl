# Usage: openroad -no_init -threads 1 -exit gen_cpp_from_odb.tcl <input.odb> [output.h]
# Generates a C++ header that reconstructs the ODB design using odb API calls.

if {$argc < 1} {
    puts "Usage: openroad -exit gen_cpp_from_odb.tcl <input.odb> \[output.h\]"
    exit 1
}
set odb_path [lindex $argv 0]
set out_path [expr {$argc >= 2 ? [lindex $argv 1] : "generated_design.h"}]

read_db $odb_path
set db [ord::get_db]
set tech [$db getTech]
set block [[$db getChip] getBlock]

# Helper: escape C++ string (brackets, backslashes, quotes)
proc cstr {s} {
    string map {\\ \\\\ \" \\\"} $s
}

set f [open $out_path w]
puts $f "// Auto-generated from $odb_path"
puts $f {#pragma once}
puts $f {#include "odb/db.h"}
puts $f {}
puts $f {namespace gen \{}
puts $f {}
puts $f {inline void buildDesign(odb::dbDatabase* db) \{}

puts $f "  auto* tech = odb::dbTech::create(db, \"tech\");"
puts $f "  tech->setManufacturingGrid([$tech getManufacturingGrid]);"

# Layers
foreach layer [$tech getLayers] {
    set name [cstr [$layer getName]]
    set type [$layer getType]
    puts $f "  \{ auto* l = odb::dbTechLayer::create(tech, \"$name\", odb::dbTechLayerType::$type);"
    if {$type == "ROUTING"} {
        puts $f "    l->setDirection(odb::dbTechLayerDir::[$layer getDirection]);"
    }
    puts $f "  \}"
}

# Lib first (site needs it)
puts $f "  auto* lib = odb::dbLib::create(db, \"lib\", tech, ',');"

# Site
set site [[lindex [$block getRows] 0] getSite]
puts $f "  auto* site = odb::dbSite::create(lib, \"[cstr [$site getName]]\");"
puts $f "  site->setWidth([$site getWidth]);"
puts $f "  site->setHeight([$site getHeight]);"

# Masters
array set seen {}
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    set mname [$master getName]
    if {![info exists seen($mname)]} {
        set seen($mname) 1
        puts $f "  \{ auto* m = odb::dbMaster::create(lib, \"[cstr $mname]\");"
        puts $f "    m->setWidth([$master getWidth]); m->setHeight([$master getHeight]);"
        puts $f "    m->setType(odb::dbMasterType::[$master getType]);"
        foreach mterm [$master getMTerms] {
            puts $f "    odb::dbMTerm::create(m, \"[cstr [$mterm getName]]\", odb::dbIoType::[$mterm getIoType], odb::dbSigType::[$mterm getSigType]);"
        }
        puts $f "    m->setFrozen(); \}"
    }
}

# Chip + Block
set die [$block getDieArea]
puts $f "  auto* chip = odb::dbChip::create(db, tech);"
puts $f "  auto* block = odb::dbBlock::create(chip, \"design\");"
puts $f "  block->setDieArea(odb::Rect([$die xMin], [$die yMin], [$die xMax], [$die yMax]));"

# Instances — use list to preserve bracket names
foreach inst [$block getInsts] {
    set iname [cstr [$inst getName]]
    set mname [cstr [[$inst getMaster] getName]]
    set ox [lindex [$inst getOrigin] 0]
    set oy [lindex [$inst getOrigin] 1]
    puts $f "  \{ auto* i = odb::dbInst::create(block, lib->findMaster(\"$mname\"), \"$iname\");"
    puts $f "    i->setOrigin($ox, $oy); i->setPlacementStatus(odb::dbPlacementStatus::[$inst getPlacementStatus]); \}"
}

# Nets
foreach net [$block getNets] {
    set nname [cstr [$net getName]]
    puts $f "  \{ auto* n = odb::dbNet::create(block, \"$nname\");"
    puts $f "    n->setSigType(odb::dbSigType::[$net getSigType]);"
    foreach iterm [$net getITerms] {
        set inst_name [cstr [[$iterm getInst] getName]]
        set mterm_name [cstr [[$iterm getMTerm] getName]]
        puts $f "    block->findInst(\"$inst_name\")->findITerm(\"$mterm_name\")->connect(n);"
    }
    foreach bterm [$net getBTerms] {
        puts $f "    odb::dbBTerm::create(n, \"[cstr [$bterm getName]]\");"
    }
    puts $f "  \}"
}

puts $f "\}"
puts $f "\}  // namespace gen"
close $f
puts "Done: [exec wc -l $out_path]"
