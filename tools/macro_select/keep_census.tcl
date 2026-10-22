# Keep census: which kept boundaries the paths over a target cut through.
# Run on a stage ODB written with OPENROAD_HIERARCHICAL=1, so the kept
# modules are dbModInsts, with timing loaded. For each register-to-register
# endpoint at or above CENSUS_TARGET (a period, in the liberty's time unit),
# its worst path is walked with the buffers left out: buffers come after
# synthesis, so what synthesis saw is the chain of logic cells. Between two
# consecutive logic cells in different module instances the path crosses a
# kept boundary in the middle of a cone, which ABC optimised in pieces,
# without the arrivals at each piece's inputs. A boundary at a register or
# at a hardened block's pin is where the cone starts or ends.
#
#   CENSUS_TARGET=2000 CENSUS_OUT=census.tsv  (source this, then keep_census)
#
# CENSUS_OUT gets one line per row, tab separated:
#   cross <module instance> <master> <paths> <excess>
#     a path crossing the instance's boundary between two logic cells, in
#     or out; excess is the sum of the paths' periods over the target
#   inside <module instance> <master> <paths> <logic delay>
#     the logic delay the paths spend in cells directly inside the instance:
#     where a cone is long and uncut, a keep added is the candidate
#   macro <block instance> <master> <paths> <excess>
#     a path launched or captured at a hardened block's pin
#   paths <count> <target> <worst period> <seconds>
# Flattening does not dominate: .claude/skills/macro-selection says how to
# read the rows, in both directions.

# A module's RTL name: hierarchical synthesis uniquifies a kept module as
# <module>$<parent>.<instance>.
proc census_module { m } {
  return [lindex [split [$m getName] $] 0]
}

# The module instance owning a cell, "" at the top. Cached per instance.
proc census_owner { inst } {
  set m [$inst getModule]
  set mi [$m getModInst]
  if { $mi eq "NULL" } { return [list "" [census_module $m]] }
  return [list [$mi getHierarchicalName] [census_module $m]]
}

proc census_add { var key n } {
  upvar $var d
  if { [dict exists $d $key] } {
    lassign [dict get $d $key] c s
    dict set d $key [list [expr { $c + 1 }] [expr { $s + $n }]]
  } else {
    dict set d $key [list 1 $n]
  }
}

proc keep_census {} {
  set t0 [clock milliseconds]
  set target $::env(CENSUS_TARGET)
  set clk [lindex [all_clocks] 0]
  set period [get_property $clk period]
  set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
  # every endpoint at or above the target: slack at most period - target
  set pes [find_timing_paths {*}$r2r -sort_by_slack -endpoint_path_count 1 \
             -group_path_count 1000000 -unique_paths_to_endpoint \
             -slack_max [expr { $period - $target }]]
  # each path as values first: names, kinds and delays; a later query may
  # free the path objects
  set paths {}
  foreach pe $pes {
    set per [expr { $period - [get_property $pe slack] }]
    set stages {}
    set prev ""
    foreach p [get_property $pe points] {
      set pin [get_property $p pin]
      set arr [get_property $p arrival]
      if { [get_property $pin direction] eq "output" } {
        lappend stages [list [get_full_name $pin] [expr { $prev eq "" ? 0.0 : $arr - $prev }]]
      }
      set prev $arr
    }
    lappend paths [list $per $stages]
  }
  set kinds [dict create]
  set blocks [dict create]
  set owners [dict create]
  set cross [dict create]
  set inside [dict create]
  set macro [dict create]
  set worst 0
  foreach path $paths {
    lassign $path per stages
    if { $per > $worst } { set worst $per }
    set excess [expr { $per - $target }]
    set seen [dict create]
    set chain {}
    foreach st $stages {
      lassign $st name delay
      set dbpin [sta::sta_to_db_pin [get_pins $name]]
      if { $dbpin eq "NULL" } { continue }
      set inst [$dbpin getInst]
      set iname [$inst getName]
      if { ![dict exists $kinds $iname] } {
        set m [$inst getMaster]
        if { [$m isBlock] } {
          set k macro
          dict set blocks $iname [$m getName]
        } elseif { [$m isSequential] } {
          set k reg
        } elseif { [regexp {^(BUF|HB)} [$m getName]] } {
          set k buf
        } else {
          set k logic
        }
        dict set kinds $iname $k
        dict set owners $iname [census_owner $inst]
      }
      set k [dict get $kinds $iname]
      if { $k eq "buf" } { continue }
      lappend chain [list $k [dict get $owners $iname] $delay $iname]
    }
    # a launch or capture at a hardened block's pin
    foreach end [list [lindex $chain 0] [lindex $chain end]] {
      if { [lindex $end 0] ne "macro" } { continue }
      set key [list [lindex $end 3] [dict get $blocks [lindex $end 3]]]
      if { ![dict exists $seen m$key] } {
        dict set seen m$key 1
        census_add macro $key $excess
      }
    }
    for { set i 0 } { $i < [llength $chain] } { incr i } {
      lassign [lindex $chain $i] k own delay
      if { $k eq "logic" } {
        # the path counts once per instance, its delay there in full
        set n [expr { [dict exists $seen i$own] ? 0 : 1 }]
        dict set seen i$own 1
        set c 0
        set s 0
        if { [dict exists $inside $own] } { lassign [dict get $inside $own] c s }
        dict set inside $own [list [expr { $c + $n }] [expr { $s + $delay }]]
      }
      if { $i == 0 } { continue }
      lassign [lindex $chain [expr { $i - 1 }]] pk pown
      if { $k ne "logic" || $pk ne "logic" } { continue }
      set a [lindex $pown 0]
      set b [lindex $own 0]
      if { $a eq $b } { continue }
      # every module instance left or entered between the two cells
      set pa [split $a /]
      set pb [split $b /]
      set j 0
      while { $j < [llength $pa] && $j < [llength $pb] && [lindex $pa $j] eq [lindex $pb $j] } {
        incr j
      }
      foreach parts [list $pa $pb] {
        for { set l [llength $parts] } { $l > $j } { incr l -1 } {
          set path [join [lrange $parts 0 [expr { $l - 1 }]] /]
          if { [dict exists $seen c$path] } { continue }
          dict set seen c$path 1
          census_add cross $path $excess
        }
      }
    }
  }
  # the masters of the crossed instances, by name
  set masters [dict create]
  foreach iname [dict keys $owners] {
    lassign [dict get $owners $iname] path master
    dict set masters $path $master
  }
  foreach mi [[ord::get_db_block] getModInsts] {
    dict set masters [$mi getHierarchicalName] [census_module [$mi getMaster]]
  }
  set f [open $::env(CENSUS_OUT) w]
  dict for { path v } $cross {
    lassign $v c s
    set master [expr { [dict exists $masters $path] ? [dict get $masters $path] : "?" }]
    puts $f [format "cross\t%s\t%s\t%d\t%.1f" $path $master $c $s]
  }
  dict for { key v } $inside {
    lassign $key path master
    lassign $v c s
    if { $path eq "" } { set path "(top)" }
    puts $f [format "inside\t%s\t%s\t%d\t%.1f" $path $master $c $s]
  }
  dict for { key v } $macro {
    lassign $key iname master
    lassign $v c s
    puts $f [format "macro\t%s\t%s\t%d\t%.1f" $iname $master $c $s]
  }
  set secs [expr { ([clock milliseconds] - $t0) / 1000.0 }]
  puts $f [format "paths\t%d\t%s\t%.1f\t%.1f" [llength $paths] $target $worst $secs]
  close $f
  puts [format "Keep census: %d paths at or above %s, worst %.1f, %d boundaries crossed mid-cone (%.1f s)" \
    [llength $paths] $target $worst [dict size $cross] $secs]
}
