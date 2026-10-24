# The clock's effect across tpu's macros, stitched (orfs_headroom's
# reports): every reg2reg endpoint's worst setup and hold path, sorted by
# where it runs (inside a tile, inside the parent, parent to tile, tile to
# its east or south neighbour, tile to parent), first as timed, then with
# the clock paths derated 5 % either way and common path pessimism
# removed. Per class: endpoints, worst setup and hold slack, and how many
# fail each, in ps.

# the macro instance a pin is in; the parent macro is tpu_rest
proc cc_where { pin where } {
  set inst [lindex [split [get_full_name $pin] /] 0]
  if { ![dict exists $where $inst] } { error "clock_check.tcl: $inst is no macro" }
  return $inst
}

proc cc_class { from to where } {
  if { $from eq $to } {
    return [expr { [dict get $where $from] eq "tpu_rest" ? "inside the parent" : "inside a tile" }]
  }
  if { [dict get $where $from] eq "tpu_rest" } { return "parent to tile" }
  if { [dict get $where $to] eq "tpu_rest" } { return "tile to parent" }
  regexp {^u_b(\d+)_(\d+)$} $from -> r1 c1
  regexp {^u_b(\d+)_(\d+)$} $to -> r2 c2
  if { $r2 == $r1 && $c2 == $c1 + 1 } { return "tile to its east" }
  if { $r2 == $r1 + 1 && $c2 == $c1 } { return "tile to its south" }
  return "tile to another tile"
}

proc cc_paths { delay where parent } {
  set out [dict create]
  foreach pe [find_timing_paths -path_delay $delay \
      -from [all_registers -clock_pins] -to [all_registers -data_pins] \
      -group_path_count [sta::endpoint_count] -endpoint_path_count 1 \
      -unique_paths_to_endpoint] {
    set class [cc_class [cc_where [get_property $pe startpoint] $where] \
      [cc_where [get_property $pe endpoint] $where] $where]
    set s [get_property $pe slack]
    if { ![dict exists $out $class] } {
      dict set out $class [list 0 $s 0]
    }
    lassign [dict get $out $class] n worst fail
    dict set out $class [list [expr { $n + 1 }] [expr { min($worst, $s) }] \
      [expr { $fail + ($s < 0) }]]
  }
  return $out
}

proc cc_table { title where parent } {
  set setup [cc_paths max $where $parent]
  set hold [cc_paths min $where $parent]
  set lines [list $title [format "%-22s %9s %12s %10s %12s %10s" class endpoints \
    "setup worst" "failing" "hold worst" "failing"]]
  foreach class [lsort [dict keys $setup]] {
    lassign [dict get $setup $class] n sw sf
    lassign [expr { [dict exists $hold $class] ? [dict get $hold $class] : {0 0 0} }] \
      hn hw hf
    lappend lines [format "%-22s %9d %12.1f %10d %12.1f %10d" $class $n $sw $sf $hw $hf]
  }
  return $lines
}

proc hr_report { where parent } {
  set lines [cc_table "as timed" $where $parent]
  set_timing_derate -early -clock 0.95
  set_timing_derate -late -clock 1.05
  set ::sta_crpr_enabled 1
  lappend lines "" {*}[cc_table "clock paths derated 5 %, CPPR on" $where $parent]
  set p [hr_period]
  lappend lines "" [format "reg2reg minimum period, derated: %.1f ps" [dict get $p period]]
  return $lines
}
