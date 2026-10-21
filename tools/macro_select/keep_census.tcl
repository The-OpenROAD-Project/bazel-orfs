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
#   cross <module instance> <master> <paths> <excess> <worst>
#     a path crossing the instance's boundary between two logic cells, in
#     or out; excess is the sum of the paths' periods over the target,
#     worst the largest: a cut whose worst is the census's worst period
#     over the target is on the worst path, and only such a cut can move
#     the period
#   inside <module instance> <master> <paths> <logic delay>
#     the logic delay the paths spend in cells directly inside the instance:
#     where a cone is long and uncut, a keep added is the candidate
#   macro <block instance> <master> <paths> <excess> <worst>
#     a path launched or captured at a hardened block's pin
#   module <module instance> <master> <cells> <area>
#     every module instance, "(top)" for the top, with the cells and the
#     area (um^2) under it, its children's included
#   edge <module instance> <module instance> <paths> <excess> <worst>
#     the pair of instances a path runs between, from the first to the
#     second, between two logic cells; "(top)" for the top
#   period <worst reg2reg period> <clock period>
#     the worst register-to-register path, whatever the target
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

# One more path at key: its count, the sum of its excess and the largest.
proc census_add { var key n } {
  upvar $var d
  if { [dict exists $d $key] } {
    lassign [dict get $d $key] c s w
    dict set d $key [list [expr { $c + 1 }] [expr { $s + $n }] [expr { max($w, $n) }]]
  } else {
    dict set d $key [list 1 $n $n]
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
  set edge [dict create]
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
      # the pair of instances the cone runs between, once per path
      if { ![dict exists $seen e$a>$b] } {
        dict set seen e$a>$b 1
        census_add edge [list $a $b] $excess
      }
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
  # every module instance's cells and area, its children's included: the
  # mass a viewer draws for it
  set dbu [[[ord::get_db] getTech] getDbUnitsPerMicron]
  set size [dict create "" [list 0 0.0]]
  foreach inst [[ord::get_db_block] getInsts] {
    set m [$inst getMaster]
    set a [expr { double([$m getWidth]) * [$m getHeight] / $dbu / $dbu }]
    set path [lindex [census_owner $inst] 0]
    set parts [split $path /]
    for { set l [llength $parts] } { $l >= 0 } { incr l -1 } {
      set p [join [lrange $parts 0 [expr { $l - 1 }]] /]
      set c 0
      set s 0.0
      if { [dict exists $size $p] } { lassign [dict get $size $p] c s }
      dict set size $p [list [expr { $c + 1 }] [expr { $s + $a }]]
    }
  }
  set f [open $::env(CENSUS_OUT) w]
  dict for { path v } $size {
    lassign $v c s
    if { $path eq "" } {
      set master [census_module [[ord::get_db_block] getTopModule]]
      set path "(top)"
    } else {
      set master [expr { [dict exists $masters $path] ? [dict get $masters $path] : "?" }]
    }
    puts $f [format "module\t%s\t%s\t%d\t%.2f" $path $master $c $s]
  }
  dict for { path v } $cross {
    lassign $v c s w
    set master [expr { [dict exists $masters $path] ? [dict get $masters $path] : "?" }]
    puts $f [format "cross\t%s\t%s\t%d\t%.1f\t%.1f" $path $master $c $s $w]
  }
  dict for { key v } $inside {
    lassign $key path master
    lassign $v c s
    if { $path eq "" } { set path "(top)" }
    puts $f [format "inside\t%s\t%s\t%d\t%.1f" $path $master $c $s]
  }
  dict for { key v } $macro {
    lassign $key iname master
    lassign $v c s w
    puts $f [format "macro\t%s\t%s\t%d\t%.1f\t%.1f" $iname $master $c $s $w]
  }
  dict for { key v } $edge {
    lassign $key a b
    lassign $v c s w
    if { $a eq "" } { set a "(top)" }
    if { $b eq "" } { set b "(top)" }
    puts $f [format "edge\t%s\t%s\t%d\t%.1f\t%.1f" $a $b $c $s $w]
  }
  # the worst reg2reg path, whatever the target
  set top [find_timing_paths {*}$r2r -sort_by_slack -group_path_count 1]
  set worst_all [expr { [llength $top] ? $period - [get_property [lindex $top 0] slack] : 0.0 }]
  puts $f [format "period\t%.1f\t%.1f" $worst_all $period]
  set secs [expr { ([clock milliseconds] - $t0) / 1000.0 }]
  puts $f [format "paths\t%d\t%s\t%.1f\t%.1f" [llength $paths] $target $worst $secs]
  close $f
  puts [format "Keep census: %d paths at or above %s, worst %.1f, %d boundaries crossed mid-cone (%.1f s)" \
    [llength $paths] $target $worst [dict size $cross] $secs]
}
