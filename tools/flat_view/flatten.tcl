# A hierarchical flow's parent stage with each hardened block's own stage
# put back in its place: one ODB of the whole design, for looking at.
#
# Every instance of a block's macro in the parent (by master name, which is
# the block's design name) is replaced by the block's cells and nets, each
# cell moved by the macro instance's placement. A block port's net joins the
# parent net on the macro pin; a net inside the block becomes
# <instance>/<net>, a cell <instance>/<cell>. The block's own macros, its
# register files and memories, stay macros: a flat view is one level deep.
# Power and ground join the parent's net of the same name.
#
# Netlist and placement only. The block's routing and power grid are not
# copied, nor is anything timed: the result is a picture of where every
# cell is, not a design to run a stage on.
#
# FLAT_STAGE         the parent's stage (floorplan place cts grt route final)
# FLAT_BLOCK_ODBS    each block's stage ODB, one per block
# FLAT_OUTPUT        the ODB written

set odb_names {
  floorplan 2_floorplan.odb
  place 3_place.odb
  cts 4_cts.odb
  grt 5_1_grt.odb
  route 5_route.odb
  final 6_final.odb
}
if { ![dict exists $odb_names $::env(FLAT_STAGE)] } {
  error "flatten.tcl: FLAT_STAGE $::env(FLAT_STAGE) is not one of [dict keys $odb_names]"
}
read_db $::env(RESULTS_DIR)/[dict get $odb_names $::env(FLAT_STAGE)]
set db [ord::get_db]
set top [ord::get_db_block]
set lef_dir [file dirname $::env(FLAT_OUTPUT)]

foreach path $::env(FLAT_BLOCK_ODBS) {
  set t0 [clock milliseconds]
  set bdb [odb::dbDatabase_create]
  odb::read_db $bdb $path
  set bblock [[$bdb getChip] getBlock]
  set bname [$bblock getName]

  set macros {}
  foreach inst [$top getInsts] {
    if { [[$inst getMaster] getName] eq $bname } { lappend macros $inst }
  }
  if { [llength $macros] == 0 } {
    error "flatten.tcl: no instance of $bname in the parent ($path)"
  }

  # The block's masters the parent has never seen, its own macros, come
  # over as LEF; each library with one is written whole.
  set libs [dict create]
  set binsts [$bblock getInsts]
  foreach binst $binsts {
    set master [$binst getMaster]
    if { [$db findMaster [$master getName]] eq "NULL" } {
      dict set libs [[$master getLib] getName] [$master getLib]
    }
  }
  dict for {lib_name lib} $libs {
    set lef [file join $lef_dir "flatten_${bname}_$lib_name.lef"]
    odb::write_macro_lef $lib $lef
    odb::read_lef $db $lef
    file delete $lef
  }

  set die [$bblock getDieArea]
  set die_x [$die xMin]
  set die_y [$die yMin]
  set die_w [$die dx]
  set die_h [$die dy]

  foreach macro $macros {
    set name [$macro getName]
    if { [$macro getOrient] ne "R0" } {
      error "flatten.tcl: $name is placed [$macro getOrient]; only R0 is copied"
    }
    set master [$macro getMaster]
    if { [$master getWidth] != $die_w || [$master getHeight] != $die_h } {
      error "flatten.tcl: $name's master is [$master getWidth] x [$master getHeight],\
        $bname's die $die_w x $die_h"
    }
    lassign [$macro getLocation] mx my
    set dx [expr { $mx - $die_x }]
    set dy [expr { $my - $die_y }]

    # each block net's parent net, by the block net's id
    set nets [dict create]
    foreach bnet [$bblock getNets] {
      set sig [$bnet getSigType]
      if { $sig eq "POWER" || $sig eq "GROUND" } {
        set net [$top findNet [$bnet getName]]
        if { $net eq "NULL" } {
          error "flatten.tcl: the parent has no $sig net [$bnet getName] for $name"
        }
        dict set nets [$bnet getId] $net
        continue
      }
      set net "NULL"
      foreach bterm [$bnet getBTerms] {
        set iterm [$macro findITerm [$bterm getName]]
        if { $iterm eq "NULL" } {
          error "flatten.tcl: $name has no pin [$bterm getName]"
        }
        set outer [$iterm getNet]
        if { $outer eq "NULL" } { continue }
        if { $net ne "NULL" && [$net getId] != [$outer getId] } {
          error "flatten.tcl: $name's ports on [$bnet getName] meet two parent nets,\
            [$net getName] and [$outer getName]"
        }
        set net $outer
      }
      if { $net eq "NULL" } {
        set net [odb::dbNet_create $top "$name/[$bnet getName]"]
        if { $net eq "NULL" } {
          error "flatten.tcl: the parent already has a net $name/[$bnet getName]"
        }
        $net setSigType $sig
      }
      dict set nets [$bnet getId] $net
    }

    foreach binst $binsts {
      set master [$db findMaster [[$binst getMaster] getName]]
      set inst [odb::dbInst_create $top $master "$name/[$binst getName]"]
      if { $inst eq "NULL" } {
        error "flatten.tcl: the parent already has an instance $name/[$binst getName]"
      }
      $inst setOrient [$binst getOrient]
      lassign [$binst getLocation] x y
      $inst setLocation [expr { $x + $dx }] [expr { $y + $dy }]
      $inst setPlacementStatus [$binst getPlacementStatus]
      foreach biterm [$binst getITerms] {
        set bnet [$biterm getNet]
        if { $bnet eq "NULL" } { continue }
        [$inst findITerm [[$biterm getMTerm] getName]] connect [dict get $nets [$bnet getId]]
      }
    }
    odb::dbInst_destroy $macro
    puts "flatten.tcl: $name <- $bname, [llength $binsts] cells,\
      [expr { ([clock milliseconds] - $t0) / 1000.0 }] s"
  }
  odb::dbDatabase_destroy $bdb
}

write_db $::env(FLAT_OUTPUT)
