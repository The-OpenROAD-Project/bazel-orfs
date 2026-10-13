# The parent's floorplan after the macro step, as JSON: every generated macro
# the plan does not name with its placement status and box, every placed
# netlist's box, how many of its cells are not FIRM and how many of those are
# core cells, and whether any such macro overlaps a netlist. The core is
# what the generator placed, the cells its .place file names; the rest of
# the netlist is its periphery, the parent's, left for global placement. The box is the FIRM cells, the array the
# plan placed. Declared beside the flow it probes.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc
set block [ord::get_db_block]
# the core: every cell a netlist's .place file names, under its instance
# (NETLISTS: the plan's <module> <instance> pairs). The block is
# generate_ram's <module>_ram (its core <module>_ram_core with the
# periphery as Verilog) inside the wrapper in the module's place, its
# cells under the wrapper's ram instance; or the module itself.
set core [dict create]
foreach {module path} $::env(NETLISTS) {
  set place ""
  foreach name [list ${module}_ram_core ${module}_ram $module] {
    if { [file exists "$::env(RESULTS_DIR)/memories/$name.place"] } {
      set place "$::env(RESULTS_DIR)/memories/$name.place"
      break
    }
  }
  if { $place eq "" } { error "leftover_macros.tcl: no .place for $module ($path)" }
  set names {}
  set f [open $place r]
  while { [gets $f pl] >= 0 } {
    if { [lindex $pl 0] ne "" } { lappend names [lindex $pl 0] }
  }
  close $f
  # the prefix: try names until one is there (a cell the parent never
  # reads is gone as dead logic)
  set prefix "$path/"
  foreach name $names {
    foreach candidate [list "$path/" "$path.ram/" "$path/ram/"] {
      if { [$block findInst "$candidate$name"] ne "NULL" } {
        set prefix $candidate
        break
      }
    }
    if { [$block findInst "$prefix$name"] ne "NULL" } { break }
  }
  foreach name $names { dict set core "$prefix$name" 1 }
}
set macros {}
array set box {}
array set loose {}
array set cells {}
array set stray {}
foreach inst [$block getInsts] {
  set b [$inst getBBox]
  if { [[$inst getMaster] isBlock] } {
    if { [$inst getPlacementStatus] ne "FIRM" || ![string match u_block* [$inst getName]] } {
      lappend macros [list [$inst getName] [$inst getPlacementStatus] [$b xMin] [$b yMin] [$b xMax] [$b yMax]]
    }
    continue
  }
  # a netlist by its instance, the wrapper's ram folded into it
  regsub {[./]ram$} [file dirname [$inst getName]] "" key
  if { ![string match u_file* $key] } { continue }
  if { ![info exists cells($key)] } {
    set loose($key) 0
    set stray($key) 0
    set cells($key) 0
  }
  incr cells($key)
  if { [$inst getPlacementStatus] ne "FIRM" } {
    incr loose($key)
    if { [dict exists $core [$inst getName]] } {
      incr stray($key)
    }
    continue
  }
  if { [info exists box($key)] } {
    lassign $box($key) x0 y0 x1 y1
    set box($key) [list [expr { min($x0, [$b xMin]) }] [expr { min($y0, [$b yMin]) }] [expr { max($x1, [$b xMax]) }] [expr { max($y1, [$b yMax]) }]]
  } else {
    set box($key) [list [$b xMin] [$b yMin] [$b xMax] [$b yMax]]
  }
}
set out [open $::env(OUTPUT_JSON) w]
puts $out "{\n  \"dbu\": [$block getDbUnitsPerMicron],\n  \"macros\": \["
set sep ""
foreach m $macros {
  lassign $m n s x0 y0 x1 y1
  puts -nonewline $out "$sep    {\"name\": \"$n\", \"status\": \"$s\", \"box\": \[$x0, $y0, $x1, $y1\]}"
  set sep ",\n"
}
puts $out "\n  \],\n  \"netlists\": \["
set sep ""
foreach k [lsort [array names box]] {
  lassign $box($k) x0 y0 x1 y1
  puts -nonewline $out "$sep    {\"name\": \"$k\", \"cells\": $cells($k), \"not_firm\": $loose($k), \"not_firm_stray\": $stray($k), \"box\": \[$x0, $y0, $x1, $y1\]}"
  set sep ",\n"
}
puts $out "\n  \]\n}"
close $out
