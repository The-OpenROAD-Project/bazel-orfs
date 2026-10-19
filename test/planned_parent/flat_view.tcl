# The miniature's flat view against what it was made from, as JSON: the
# parent's global route (this run's src), each block's CTS stage
# (BLOCK_ODBS) and the flat ODB (FLAT_ODB). For each block's macro
# instance in the parent: whether it is gone from the flat view, the
# block's cells against the cells under <instance>/, those outside the
# macro's footprint, and the macro pins whose parent net reaches no cell
# under <instance>/ in the flat view.
read_db $::env(RESULTS_DIR)/5_1_grt.odb
set parent [ord::get_db_block]
set flat_db [odb::dbDatabase_create]
odb::read_db $flat_db $::env(FLAT_ODB)
set flat [[$flat_db getChip] getBlock]

set out {}
foreach path $::env(BLOCK_ODBS) {
  set bdb [odb::dbDatabase_create]
  odb::read_db $bdb $path
  set bblock [[$bdb getChip] getBlock]
  set bname [$bblock getName]
  set cells [llength [$bblock getInsts]]
  foreach macro [$parent getInsts] {
    if { [[$macro getMaster] getName] ne $bname } { continue }
    set name [$macro getName]
    set box [$macro getBBox]
    set copied 0
    set outside 0
    foreach inst [$flat getInsts] {
      if { ![string match "$name/*" [$inst getName]] } { continue }
      incr copied
      set b [$inst getBBox]
      if {
        [$b xMin] < [$box xMin] || [$b yMin] < [$box yMin]
        || [$b xMax] > [$box xMax] || [$b yMax] > [$box yMax]
      } {
        incr outside
      }
    }
    set unjoined 0
    set pins 0
    foreach iterm [$macro getITerms] {
      set net [$iterm getNet]
      if { $net eq "NULL" || [$net getSigType] in {POWER GROUND} } { continue }
      incr pins
      set fnet [$flat findNet [$net getName]]
      set reached 0
      if { $fnet ne "NULL" } {
        foreach fi [$fnet getITerms] {
          if { [string match "$name/*" [[$fi getInst] getName]] } {
            set reached 1
            break
          }
        }
      }
      if { !$reached } { incr unjoined }
    }
    set left [expr { [$flat findInst $name] ne "NULL" }]
    lappend out [format {{"instance": "%s", "block": "%s", "macro_left": %d, "block_cells": %d, "copied": %d, "outside": %d, "pins": %d, "unjoined": %d}} \
      $name $bname $left $cells $copied $outside $pins $unjoined]
  }
  odb::dbDatabase_destroy $bdb
}
set f [open $::env(OUTPUT_JSON) w]
puts $f "\[[join $out ",\n"]\]"
close $f
