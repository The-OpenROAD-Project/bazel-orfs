# The sets top_level.tcl's crossing report is timed in (CROSSING_SETS),
# drawn from the routed top level of a parent macro (parent_macro.bzl).
# A register-to-register path between macros runs through a set of them,
# its signature (OpenROAD's crossing_signatures, one pass, no path
# enumerated); a set of blocks times every path whose signature it holds
# (crossing_cones.tcl). The signatures are packed into sets, largest
# first, each set's estimated size (the sum of its blocks' cones) under
# PLAN_BUDGET instances; sets may overlap. Each line: the set's blocks.
#
#   PLAN_BUDGET     instances per set, the measure of a child's memory
#   CROSSING_SETS   the file to write
#   CROSSING_SIGNATURES  the signatures, with their endpoint counts
#   TOP_DIR         the routed top level's directory (top_level.tcl's
#                   output under Bazel); RESULTS_DIR by default
source $::env(SCRIPTS_DIR)/load.tcl
if { [env_var_exists_and_non_empty TOP_DIR] } {
  set ::env(RESULTS_DIR) $::env(TOP_DIR)
  load_design 5_top_grt.odb 5_top_grt.sdc
} else {
  load_design 5_top_grt.odb 2_floorplan.sdc
}
set parent [env_var_or_empty PARENT_INST]
if { $parent eq "" } {
  set parent u_parent
}

set signatures [sta::crossing_signatures $parent 1024]
set f [open $::env(CROSSING_SIGNATURES) w]
puts -nonewline $f $signatures
close $f

# a signature's blocks: its macros but the parent and the top level
set sigs {}
set blocks [dict create]
foreach line [split [string trim $signatures] "\n"] {
  lassign $line count names
  set bs {}
  foreach m [split $names +] {
    if { $m ne $parent && $m ne "top" } {
      lappend bs $m
      dict set blocks $m 1
    }
  }
  if { [llength $bs] } {
    lappend sigs [list $count [lsort $bs]]
  }
}
puts "crossing_plan: [llength $sigs] signatures over [dict size $blocks] blocks"

# each block's cones, the estimate of a set's size
set size [dict create]
foreach b [dict keys $blocks] {
  lassign [sta::crossing_cones $b $parent 1] seeds kept
  dict set size $b $kept
  puts "crossing_plan: $b $kept instances"
}
proc estimate { bs } {
  set n 0
  foreach b $bs {
    incr n [dict get $::size $b]
  }
  return $n
}

# largest signatures first; one already covered is skipped, else it joins
# the first set it fits in under the budget, else starts a set
set budget $::env(PLAN_BUDGET)
set sets {}
foreach sig [lsort -integer -decreasing -command {apply {{a b} {
  expr { [estimate [lindex $a 1]] - [estimate [lindex $b 1]] }
}}} $sigs] {
  set bs [lindex $sig 1]
  set placed 0
  foreach s $sets {
    if { [llength [lmap b $bs { if { $b in $s } continue; set b }]] == 0 } {
      set placed 1
      break
    }
  }
  if { $placed } { continue }
  for { set i 0 } { $i < [llength $sets] } { incr i } {
    set union [lsort -unique [concat [lindex $sets $i] $bs]]
    if { [estimate $union] <= $budget } {
      lset sets $i $union
      set placed 1
      break
    }
  }
  if { !$placed } {
    lappend sets $bs
  }
}

set f [open $::env(CROSSING_SETS) w]
puts $f "# one set per line: every signature is held by one of them"
foreach s $sets {
  lassign [sta::crossing_cones $s $parent 1] seeds kept before
  puts "crossing_plan: set {$s} $kept of $before instances (estimate [estimate $s])"
  puts $f $s
}
close $f

# every signature held by some set
foreach sig $sigs {
  set bs [lindex $sig 1]
  set held 0
  foreach s $sets {
    if { [llength [lmap b $bs { if { $b in $s } continue; set b }]] == 0 } {
      set held 1
    }
  }
  if { !$held } {
    utl::error FLW 30 "crossing_plan: no set holds the signature $bs"
  }
}
