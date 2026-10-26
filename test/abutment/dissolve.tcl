# A macro dissolved into its cells, right after tapcell (POST_TAPCELL_TCL):
# every instance of DISSOLVE_MASTER becomes the cells, nets and rows of
# the macro's own placed design, DISSOLVE_ODB, at the instance's
# location, FIRM (DEF's FIXED). The macro was built to be placed only: from here on
# its cells are the parent's, timed, clocked and powered with the
# parent's own, and nothing moves or resizes them.
#
# The macro's rows come with it, so the parent's grid draws its rails
# over them and the legaliser puts the parent's new cells, CTS buffers
# among them, in the gaps between them. The parent's rows were cut
# around the macro by tapcell (cut_rows, MACRO_ROWS_HALO_X/Y 0), so the
# macro's rows fill the hole exactly, its own tap and end cap cells on
# them.
#
# A cell or net is named <instance>.<its name>, as yosys names the cells
# of a flattened module: the parent is read hierarchically (read_db
# -hier), and there STA takes a / in a flat name for a hierarchy divider
# and keeps only what follows the last one, so every tile's copy of a
# cell would have the same name in reports, netlists and parasitics.
#
# A port net is the parent's net on the macro's pin; a feedthrough, a
# net on two of the macro's ports, merges the two parent nets. The
# parent must be flat (OPENROAD_HIERARCHICAL 0): no module nets.

set block [ord::get_db_block]
set db [ord::get_db]
set master_name $::env(DISSOLVE_MASTER)

set src_db [odb::dbDatabase_create]
odb::read_db $src_db $::env(DISSOLVE_ODB)
set src [[$src_db getChip] getBlock]

# the parent's sites by name, and the row parity: a row's orientation
# is R0 or MX by its distance from a parent row, in rows
set sites [dict create]
foreach lib [$db getLibs] {
  foreach site [$lib getSites] { dict set sites [$site getName] $site }
}
set ref_row [lindex [$block getRows] 0]
set ref_y [[$ref_row getBBox] yMin]
set ref_o [$ref_row getOrient]
set row_h [[$ref_row getSite] getHeight]
proc dissolve_row_orient { y ref_y ref_o row_h } {
  set d [expr { ($y - $ref_y) / $row_h }]
  if { ($y - $ref_y) % $row_h != 0 } { return "" }
  if { $d % 2 == 0 } { return $ref_o }
  return [expr { $ref_o eq "R0" ? "MX" : "R0" }]
}

proc dissolve_move { from to } {
  # every pin of net $from onto net $to; $from goes
  foreach it [$from getITerms] { $it connect $to }
  foreach bt [$from getBTerms] { $bt connect $to }
  odb::dbNet_destroy $from
}

set macros {}
foreach inst [$block getInsts] {
  if { [[$inst getMaster] getName] eq $master_name } { lappend macros $inst }
}
if { [llength $macros] == 0 } {
  utl::error FLW 701 "dissolve.tcl: no instance of $master_name"
}

set n_cells 0
set n_rows 0
set n_merged 0
foreach macro $macros {
  set path [$macro getName]
  if { [$macro getOrient] ne "R0" } {
    utl::error FLW 702 "dissolve.tcl: $path is [$macro getOrient], only R0 dissolves"
  }
  lassign [$macro getLocation] X Y
  # the parent's net on each of the macro's pins
  set port_net [dict create]
  foreach it [$macro getITerms] {
    if { [$it getModNet] ne "NULL" } {
      utl::error FLW 703 "dissolve.tcl: [$it getName] is on a module net;\
        the parent must be flat"
    }
    set net [$it getNet]
    if { $net ne "NULL" && ![$net isSpecial] } {
      dict set port_net [[$it getMTerm] getName] $net
    }
  }
  # the macro placer's or tapcell's blockages tied to the macro go with it
  foreach bl [$block getBlockages] {
    set owner [$bl getInstance]
    if { $owner ne "NULL" && [$owner getId] == [$macro getId] } {
      odb::dbBlockage_destroy $bl
    }
  }
  odb::dbInst_destroy $macro

  # nets: the parent's for a port net, a new one for the rest
  set nets [dict create]
  foreach net [$src getNets] {
    if { [$net isSpecial] } { continue }
    set outer {}
    foreach bt [$net getBTerms] {
      if { [dict exists $port_net [$bt getName]] } {
        set pn [dict get $port_net [$bt getName]]
        if { $pn ni $outer } { lappend outer $pn }
      }
    }
    if { [llength $outer] == 0 } {
      set pn [odb::dbNet_create $block "$path.[$net getName]"]
      $pn setSigType [$net getSigType]
    } else {
      set pn [lindex $outer 0]
      foreach other [lrange $outer 1 end] {
        dissolve_move $other $pn
        incr n_merged
      }
    }
    dict set nets [$net getName] $pn
  }

  foreach inst [$src getInsts] {
    set mname [[$inst getMaster] getName]
    set m [$db findMaster $mname]
    if { $m eq "NULL" } {
      utl::error FLW 704 "dissolve.tcl: no master $mname for $path.[$inst getName]"
    }
    set new [odb::dbInst_create $block $m "$path.[$inst getName]"]
    $new setOrient [$inst getOrient]
    lassign [$inst getLocation] x y
    $new setLocation [expr { $X + $x }] [expr { $Y + $y }]
    $new setPlacementStatus FIRM
    foreach it [$inst getITerms] {
      set net [$it getNet]
      if { $net eq "NULL" || [$net isSpecial] } { continue }
      [$new findITerm [[$it getMTerm] getName]] connect [dict get $nets [$net getName]]
    }
    incr n_cells
  }

  foreach row [$src getRows] {
    set site_name [[$row getSite] getName]
    if { ![dict exists $sites $site_name] } {
      utl::error FLW 705 "dissolve.tcl: no site $site_name for $path's rows"
    }
    lassign [$row getOrigin] x y
    set y [expr { $Y + $y }]
    set want [dissolve_row_orient $y $ref_y $ref_o $row_h]
    if { $want ne [$row getOrient] } {
      utl::error FLW 706 "dissolve.tcl: $path's row [$row getName] at y\
        [expr { $y / double([$block getDbUnitsPerMicron]) }] um is\
        [$row getOrient], the parent's row there would be '$want':\
        place the macro an even number of rows from the parent's"
    }
    odb::dbRow_create $block "$path.[$row getName]" [dict get $sites $site_name] \
      [expr { $X + $x }] $y [$row getOrient] HORIZONTAL \
      [$row getSiteCount] [$row getSpacing]
    incr n_rows
  }
}

# the macro's rows fill the holes tapcell cut, exactly: an overlap means
# a halo or a misplaced macro
set boxes {}
foreach row [$block getRows] { lappend boxes [$row getBBox] }
for { set i 0 } { $i < [llength $boxes] } { incr i } {
  set a [lindex $boxes $i]
  for { set j [expr { $i + 1 }] } { $j < [llength $boxes] } { incr j } {
    set b [lindex $boxes $j]
    if {
      [$a yMin] == [$b yMin] && [$a xMin] < [$b xMax] && [$b xMin] < [$a xMax]
    } {
      utl::error FLW 707 "dissolve.tcl: rows overlap at y [$a yMin]"
    }
  }
}

odb::dbDatabase_destroy $src_db
utl::info FLW 708 "dissolve.tcl: [llength $macros] $master_name dissolved,\
  $n_cells cells FIRM, $n_rows rows, $n_merged feedthrough nets merged"
