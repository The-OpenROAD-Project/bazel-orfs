# One part's snapshot for the kit (kit/README: "OpenROAD reference"): what
# its global-route checkpoint holds, read without timing, so a part loads
# in minutes and in a fraction of the memory its stage took. Into
# $RUN_OUTPUT_DIR:
#
#   stats.json      die, core, instance and cell counts, areas, utilisation
#   macros.csv      every block-master instance: name, master, box (um), orientation
#   pins.csv        every signal port: name, direction, layer, box (um)
#   modules.csv     standard-cell area per bin per module, depths 1 to 5
#   density.csv     standard-cell area per bin over bin area, row by row from the bottom
#   floorplan.png   macros, ports and power straps (at the whole die the
#                   viewer draws no standard cell; density.csv and
#                   modules.png show where they are)
#   congestion.png  global-route congestion over the layout
#   modules.png     cells coloured by the module they belong to
#
# Run by orfs_run on <part>_grt (kit.bzl, xs_kit_snapshot). SNAPSHOT_BIN_UM
# is the density bin, SNAPSHOT_WIDTH the images' width in pixels.

set out $::env(RUN_OUTPUT_DIR)
file mkdir $out
read_db $::env(RESULTS_DIR)/5_1_grt.odb
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
proc um { v } { return [format "%.4f" [expr { double($v) / $::dbu }]] }
proc box_um { b } {
  return [list [um [$b xMin]] [um [$b yMin]] [um [$b xMax]] [um [$b yMax]]]
}
proc csv { s } {
  if { [string first "," $s] >= 0 || [string first "\"" $s] >= 0 } {
    return "\"[string map {\" \"\"} $s]\""
  }
  return $s
}

# ---- macros and cells ----
set mf [open $out/macros.csv w]
puts $mf "name,master,x0,y0,x1,y1,orient,status"
set cells 0
set macros 0
set cell_area 0.0
set macro_area 0.0
set flops 0
set bin [expr { [info exists ::env(SNAPSHOT_BIN_UM)] ? double($::env(SNAPSHOT_BIN_UM)) : 20.0 }]
set die [$block getDieArea]
set core [$block getCoreArea]
set nx [expr { int(ceil(double([$die dx]) / $dbu / $bin)) }]
set ny [expr { int(ceil(double([$die dy]) / $dbu / $bin)) }]
array set dens {}
# modules.csv: standard-cell area per bin per module, at hierarchy depths 1
# to 5 (an instance's path without its leaf, split at the kept
# hierarchy's / and a flattened module's .)
array set modarea {}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set b [$inst getBBox]
  if { [$m isBlock] } {
    puts $mf [join [list [csv [string map {\\ ""} [$inst getName]]] [$m getName] {*}[box_um $b] [$inst getOrient] [$inst getPlacementStatus]] ,]
    incr macros
    set macro_area [expr { $macro_area + double([$b getDX]) * [$b getDY] / $dbu / $dbu }]
    continue
  }
  if { [$m getType] ne "CORE" } { continue }
  incr cells
  set a [expr { double([$m getWidth]) * [$m getHeight] / $dbu / $dbu }]
  set cell_area [expr { $cell_area + $a }]
  if { [$m isSequential] } { incr flops }
  set i [expr { int((([$b xMin] + [$b xMax]) / 2.0 - [$die xMin]) / $dbu / $bin) }]
  set j [expr { int((([$b yMin] + [$b yMax]) / 2.0 - [$die yMin]) / $dbu / $bin) }]
  set k "$i,$j"
  set path [lrange [split [string map {\\ ""} [$inst getName]] "/."] 0 end-1]
  for { set d 1 } { $d <= 5 && $d <= [llength $path] } { incr d } {
    set mk "$d,$i,$j,[join [lrange $path 0 [expr { $d - 1 }]] /]"
    if { [info exists modarea($mk)] } {
      set modarea($mk) [expr { $modarea($mk) + $a }]
    } else {
      set modarea($mk) $a
    }
  }
  if { [info exists dens($k)] } {
    set dens($k) [expr { $dens($k) + $a }]
  } else {
    set dens($k) $a
  }
}
close $mf

set mf [open $out/modules.csv w]
puts $mf "depth,i,j,module,area_um2"
foreach mk [array names modarea] {
  lassign [split $mk ,] d i j
  set name [join [lrange [split $mk ,] 3 end] ,]
  puts $mf "$d,$i,$j,[csv $name],[format %.3f $modarea($mk)]"
}
close $mf
array unset modarea

set df [open $out/density.csv w]
puts $df "# bin_um $bin nx $nx ny $ny; standard-cell area per bin over the bin's area, row j=0 at the die's bottom"
for { set j 0 } { $j < $ny } { incr j } {
  set row {}
  for { set i 0 } { $i < $nx } { incr i } {
    set v [expr { [info exists dens($i,$j)] ? $dens($i,$j) / ($bin * $bin) : 0.0 }]
    lappend row [format "%.4f" $v]
  }
  puts $df [join $row ,]
}
close $df

# ---- ports ----
set pf [open $out/pins.csv w]
puts $pf "name,direction,layer,x0,y0,x1,y1"
set ports 0
foreach bterm [$block getBTerms] {
  set t [$bterm getSigType]
  if { $t ne "SIGNAL" && $t ne "CLOCK" } { continue }
  foreach bpin [$bterm getBPins] {
    foreach b [$bpin getBoxes] {
      puts $pf [join [list [csv [$bterm getName]] [$bterm getIoType] [[$b getTechLayer] getName] {*}[box_um $b]] ,]
    }
  }
  incr ports
}
close $pf

set core_um2 [expr { double([$core dx]) * [$core dy] / $dbu / $dbu }]
set f [open $out/stats.json w]
puts $f "{"
puts $f "  \"design\": \"[$block getName]\","
puts $f "  \"die_um\": \[[join [box_um $die] ,]\],"
puts $f "  \"core_um\": \[[join [box_um $core] ,]\],"
puts $f "  \"std_cells\": $cells,"
puts $f "  \"flops\": $flops,"
puts $f "  \"std_cell_area_um2\": [format %.1f $cell_area],"
puts $f "  \"macro_instances\": $macros,"
puts $f "  \"macro_area_um2\": [format %.1f $macro_area],"
puts $f "  \"core_area_um2\": [format %.1f $core_um2],"
puts $f "  \"utilization\": [format %.4f [expr { $cell_area / max(1.0, $core_um2 - $macro_area) }]],"
puts $f "  \"signal_ports\": $ports,"
puts $f "  \"nets\": [llength [$block getNets]],"
puts $f "  \"density_bin_um\": $bin,"
puts $f "  \"dbu_per_um\": $dbu"
puts $f "}"
close $f

# ---- the pins of the blocks' abstracts, as this part sees them ----
# SNAPSHOT_MASTER_PINS names the masters (the hardened blocks in the
# parent): each pin's shapes relative to the master's origin.
if { [info exists ::env(SNAPSHOT_MASTER_PINS)] && $::env(SNAPSHOT_MASTER_PINS) ne "" } {
  set mp [open $out/master_pins.csv w]
  puts $mp "master,pin,direction,layer,x0,y0,x1,y1,width,height"
  foreach name $::env(SNAPSHOT_MASTER_PINS) {
    set master [[ord::get_db] findMaster $name]
    if { $master eq "NULL" } { error "snapshot: no master $name in [$block getName]" }
    foreach mterm [$master getMTerms] {
      set t [$mterm getSigType]
      if { $t ne "SIGNAL" && $t ne "CLOCK" } { continue }
      foreach mpin [$mterm getMPins] {
        foreach b [$mpin getGeometry] {
          set layer [$b getTechLayer]
          if { $layer eq "NULL" } { continue }
          puts $mp [join [list $name [csv [$mterm getName]] [$mterm getIoType] [$layer getName] {*}[box_um $b] [um [$master getWidth]] [um [$master getHeight]]] ,]
        }
      }
    }
  }
  close $mp
}

# ---- global route's own congestion report, from the stage's log ----
if { [info exists ::env(LOG_DIR)] && [file exists $::env(LOG_DIR)/5_1_grt.log] } {
  set lf [open $::env(LOG_DIR)/5_1_grt.log]
  set keep 0
  set lines {}
  while { [gets $lf line] >= 0 } {
    if { [string match "*GRT-0096*" $line] } { set keep 1; set lines {} }
    if { $keep } { lappend lines $line }
    if { $keep && [string match "*GRT-0018*" $line] } { set keep 0 }
  }
  close $lf
  set cf [open $out/congestion.txt w]
  puts $cf [join $lines "\n"]
  close $cf
}

# ---- images ----
set w [expr { [info exists ::env(SNAPSHOT_WIDTH)] ? $::env(SNAPSHOT_WIDTH) : 2048 }]
set quiet {-display_option {routing false} -display_option {special_nets false} -display_option {net_power false}}
foreach {name opts} [list \
  floorplan [concat $quiet {-display_option {stdcells false}}] \
  congestion [concat $quiet {-display_option {routing_congestion true}}] \
  modules [concat $quiet {-display_option {module_view true}}]] {
  if { [catch { save_image -web -width $w {*}$opts $out/$name.png } err] } {
    puts "snapshot: $name.png not drawn: $err"
  }
}
puts "snapshot: [$block getName]: $cells cells, [format %.0f $macro_area] um2 of macros, $ports ports"
