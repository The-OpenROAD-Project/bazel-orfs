# What the macro step left of test/regfile's regfile_top register file, as JSON:
# whether the RegFile macro is gone, its cells by kind, and the facts
# check_dissolve.py asserts. The core is the cells memories/RegFile.place
# names; the rest under u_rf/ is the periphery.
# The stage's ODB is ODB_FILE, in another repository's results directory:
# read it directly, and the generator's files from beside it.
read_db $::env(ODB_FILE)
set block [ord::get_db_block]
set place [dict create]
set f [open [file dirname $::env(ODB_FILE)]/memories/RegFile.place r]
while { [gets $f line] >= 0 } {
  if { [lindex $line 0] ne "" } { dict set place "u_rf/[lindex $line 0]" 1 }
}
close $f
set row_orient [dict create]
foreach row [$block getRows] {
  dict set row_orient [[$row getBBox] yMin] [$row getOrient]
}
set macros 0
set core 0
set core_firm 0
set core_dont_touch 0
set core_flops 0
set off_row 0
set periphery 0
set periphery_placed 0
set stray_firm 0
foreach inst [$block getInsts] {
  set master [$inst getMaster]
  if { [$master getName] eq "RegFile" } { incr macros }
  set name [$inst getName]
  if { ![string match u_rf/* $name] } { continue }
  if { [dict exists $place $name] } {
    incr core
    if { [$inst getPlacementStatus] eq "FIRM" } { incr core_firm }
    if { [$inst isDoNotTouch] } { incr core_dont_touch }
    if { [$master isSequential] } { incr core_flops }
    set y [[$inst getBBox] yMin]
    if { ![dict exists $row_orient $y] } {
      incr off_row
    } else {
      # a cell flipped about x sits on an MX row, an upright one on an R0 row
      set ro [expr { [dict get $row_orient $y] in {R0 MY} ? "R0" : "MX" }]
      set co [expr { [$inst getOrient] in {R0 MY} ? "R0" : "MX" }]
      if { $ro ne $co } { incr off_row }
    }
  } else {
    incr periphery
    if { [$inst isPlaced] } { incr periphery_placed }
    if { [$inst getPlacementStatus] eq "FIRM" } { incr stray_firm }
  }
}
set internal_nets 0
foreach net [$block getNets] {
  if { [string match u_rf/* [$net getName]] && [$net isDoNotTouch] } { incr internal_nets }
}
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"place_lines\": [dict size $place],"
puts $out "  \"macros\": $macros,"
puts $out "  \"core\": $core,"
puts $out "  \"core_firm\": $core_firm,"
puts $out "  \"core_dont_touch\": $core_dont_touch,"
puts $out "  \"core_flops\": $core_flops,"
puts $out "  \"core_off_row\": $off_row,"
puts $out "  \"periphery\": $periphery,"
puts $out "  \"periphery_placed\": $periphery_placed,"
puts $out "  \"periphery_firm\": $stray_firm,"
puts $out "  \"internal_nets_dont_touch\": $internal_nets"
puts $out "}"
close $out
