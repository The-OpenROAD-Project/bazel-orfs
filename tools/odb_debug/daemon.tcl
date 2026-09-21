# odb-debug daemon: a persistent OpenROAD session on a stage ODB, answering
# Tcl over a localhost socket, so a person or an agent can ask a placed or
# routed design questions without paying the ODB and liberty load for each.
#
# Run it as a flow stage's companion so it gets the flow's exact environment
# (ODB, SDC, liberty set, RC, derates), either through bazel
#
#   bazelisk run //my:design_place_odb_debug -- ODB_DEBUG_DIR=$PWD/tmp/odb-debug
#
# or from a deployed `_deps` tree, where the checkpoint of an unfinished or
# failed stage can be dropped into results/ and opened directly:
#
#   ./make run RUN_SCRIPT=$PWD/tools/odb_debug/daemon.tcl \
#       ODB_FILE=<results>/3_4_place_resized.odb ODB_DEBUG_DIR=$PWD/tmp/odb-debug
#
# GUI_TIMING=0 skips the liberty files: a 2.5 GB, 1.35 M-instance ODB then
# loads in seconds and a few GB, and every geometry query works; the timing
# queries answer that no timing is loaded. Without it the design's liberty
# set loads and the timing queries work too.
#
# Protocol, one request per line: the line is base64 of UTF-8 Tcl, evaluated
# at global scope. The reply is one JSON line:
#   {"ok":true,"result":"<string>","stdout":"<string>","ms":<int>}
#   {"ok":false,"error":"<message>","stdout":"<string>","ms":<int>}
# The od_* procs return JSON strings, so a client decodes .result. Anything
# else is fair game; the session has the trust model of an interactive
# `openroad` shell on the same machine. It listens on 127.0.0.1 only.
#
# Files, all under ODB_DEBUG_DIR (required): daemon.json, written when the
# socket is ready -- port, pid, design, odb, workspace, commit, timing --
# and removed when the daemon exits on its own. ODB_DEBUG_IDLE_SECS is the
# idle time before it exits (0 disables; default twice the load time, at
# least 120 s), so a forgotten daemon gives its memory back.

set ::od_t0 [clock milliseconds]

if { ![info exists ::env(ODB_DEBUG_DIR)] || $::env(ODB_DEBUG_DIR) eq "" } {
  error "ODB_DEBUG_DIR must be set, e.g. ODB_DEBUG_DIR=\$PWD/tmp/odb-debug"
}
file mkdir $::env(ODB_DEBUG_DIR)

# Attach to a design a GUI session already holds; otherwise load the stage
# the way the flow does.
set ::od_attached 0
catch { if { [ord::get_db_block] ne "NULL" } { set ::od_attached 1 } }
if { !$::od_attached } {
  source $::env(SCRIPTS_DIR)/open.tcl
}
set ::od_load_secs [expr { ([clock milliseconds] - $::od_t0) / 1000.0 }]

# Timing is available when liberty loaded and STA sees registers. Ask
# whether liberty was loaded before asking STA anything: with GUI_TIMING=0
# it was not, and the first STA query prints
#
#     [ERROR STA-2141] No liberty libraries found.
#
# before it throws, which reads as a failure in every launch log although
# the session went on without timing, as intended. The question is STA's
# own predicate, not the database's getLibs -- those are the LEF libs,
# which an ODB always carries, liberty or no liberty. If a build has no
# such predicate the fallback is the old behaviour: ask STA and catch.
set has_liberty 1
catch { set has_liberty [sta::liberty_libraries_exist] }
set ::od_timing 0
if { $has_liberty } {
  catch { if { [llength [all_registers]] > 0 } { set ::od_timing 1 } }
}

# ---- JSON ------------------------------------------------------------------

proc od_jstr { s } {
  set s [string map {"\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "\\r" "\t" "\\t"} $s]
  return "\"$s\""
}
proc od_jnum { v } {
  if { $v eq "" } { return null }
  if { [string is integer -strict $v] } { return $v }
  if { [string is double -strict $v] } { return [format %.6g $v] }
  return [od_jstr $v]
}
proc od_jobj { pairs } {
  set parts {}
  foreach {k v} $pairs { lappend parts "[od_jstr $k]:$v" }
  return "{[join $parts ,]}"
}
proc od_jarr { items } { return "\[[join $items ,]\]" }
proc od_jbool { v } { return [expr { $v ? "true" : "false" }] }

proc od_um { dbu_value } {
  return [format %.4f [expr { double($dbu_value) / [[ord::get_db_tech] getDbUnitsPerMicron] }]]
}
proc od_box_json { rect } {
  return [od_jarr [list [od_um [$rect xMin]] [od_um [$rect yMin]] [od_um [$rect xMax]] [od_um [$rect yMax]]]]
}

proc od_require_timing {} {
  if { !$::od_timing } {
    error "no timing loaded: the daemon was started with GUI_TIMING=0, or no liberty matched; geometry queries still work"
  }
}

# ---- Design ----------------------------------------------------------------

proc od_status {} {
  set blk [ord::get_db_block]
  set macros 0
  foreach i [$blk getInsts] { if { [[$i getMaster] isBlock] } { incr macros } }
  return [od_jobj [list \
    design [od_jstr [$blk getName]] \
    odb [od_jstr [expr { [info exists ::env(ODB_FILE)] ? $::env(ODB_FILE) : "" }]] \
    workspace [od_jstr $::od_workspace] \
    commit [od_jstr $::od_commit] \
    timing [od_jbool $::od_timing] \
    load_secs [od_jnum $::od_load_secs] \
    insts [llength [$blk getInsts]] \
    macros $macros \
    nets [llength [$blk getNets]] \
    rows [llength [$blk getRows]] \
    blockages [llength [$blk getBlockages]] \
    die [od_box_json [$blk getDieArea]] \
    core [od_box_json [$blk getCoreArea]]]]
}

# Every macro (CLASS BLOCK) instance: name, master, box in um, orientation,
# placement status. The floorplan's skeleton.
proc od_macros {} {
  set items {}
  foreach i [[ord::get_db_block] getInsts] {
    set m [$i getMaster]
    if { ![$m isBlock] } { continue }
    lappend items [od_jobj [list name [od_jstr [$i getName]] master [od_jstr [$m getName]] \
      box [od_box_json [$i getBBox]] orient [od_jstr [$i getOrient]] status [od_jstr [$i getPlacementStatus]]]]
  }
  return [od_jarr $items]
}

# One instance: master, location, size, status, and whether its centre lies
# inside a macro's box (the legaliser has to move it out).
proc od_cell { name } {
  set blk [ord::get_db_block]
  set i [$blk findInst $name]
  if { $i eq "NULL" } { error "no instance named $name" }
  set m [$i getMaster]
  set b [$i getBBox]
  set cx [expr { ([$b xMin] + [$b xMax]) / 2 }]
  set cy [expr { ([$b yMin] + [$b yMax]) / 2 }]
  set inside ""
  foreach j [$blk getInsts] {
    if { ![[$j getMaster] isBlock] || $j eq $i } { continue }
    set mb [$j getBBox]
    if { $cx > [$mb xMin] && $cx < [$mb xMax] && $cy > [$mb yMin] && $cy < [$mb yMax] } {
      set inside [$j getName]
      break
    }
  }
  return [od_jobj [list name [od_jstr [$i getName]] master [od_jstr [$m getName]] \
    box [od_box_json $b] orient [od_jstr [$i getOrient]] status [od_jstr [$i getPlacementStatus]] \
    is_macro [od_jbool [$m isBlock]] inside_macro [od_jstr $inside]]]
}

# One net: driver, pin count, and the box the pins span.
proc od_net { name } {
  set blk [ord::get_db_block]
  set n [$blk findNet $name]
  if { $n eq "NULL" } { error "no net named $name" }
  set driver ""
  set pins {}
  set xmin ""
  foreach it [$n getITerms] {
    set inst [$it getInst]
    lappend pins [od_jstr "[$inst getName]/[[$it getMTerm] getName]"]
    if { [[$it getIoType] == "OUTPUT"] } { set driver "[$inst getName]/[[$it getMTerm] getName]" }
    set b [$inst getBBox]
    set x [expr { ([$b xMin] + [$b xMax]) / 2 }]
    set y [expr { ([$b yMin] + [$b yMax]) / 2 }]
    if { $xmin eq "" } { set xmin $x; set xmax $x; set ymin $y; set ymax $y } else {
      set xmin [expr { min($xmin, $x) }]; set xmax [expr { max($xmax, $x) }]
      set ymin [expr { min($ymin, $y) }]; set ymax [expr { max($ymax, $y) }]
    }
  }
  foreach bt [$n getBTerms] { lappend pins [od_jstr "port:[$bt getName]"] }
  set span [expr { $xmin eq "" ? "null" : [od_jarr [list [od_um $xmin] [od_um $ymin] [od_um $xmax] [od_um $ymax]]] }]
  return [od_jobj [list name [od_jstr [$n getName]] driver [od_jstr $driver] pins [llength $pins] \
    span_um $span pin_names [od_jarr [lrange $pins 0 63]]]]
}

# Placement legality, the summary the flow prints and the count of
# instances whose centre lies inside a macro box.
proc od_check_placement {} {
  set blk [ord::get_db_block]
  set macros {}
  foreach i [$blk getInsts] { if { [[$i getMaster] isBlock] } { lappend macros [$i getBBox] } }
  set inside 0
  set unplaced 0
  set total 0
  foreach i [$blk getInsts] {
    set m [$i getMaster]
    if { [$m isBlock] } { continue }
    incr total
    if { ![$i isPlaced] } { incr unplaced; continue }
    set b [$i getBBox]
    set cx [expr { ([$b xMin] + [$b xMax]) / 2 }]
    set cy [expr { ([$b yMin] + [$b yMax]) / 2 }]
    foreach mb $macros {
      if { $cx > [$mb xMin] && $cx < [$mb xMax] && $cy > [$mb yMin] && $cy < [$mb yMax] } { incr inside; break }
    }
  }
  set report [od_capture {check_placement -verbose}]
  return [od_jobj [list insts $total unplaced $unplaced inside_macro $inside check_placement [od_jstr $report]]]
}

# Dump the geometry to text files for offline analysis (tools/odb_debug/
# geometry.py): summary.txt, rows.txt (row fragments: x0 y0 x1 y1 sites,
# in dbu), macros.txt (name master x0 y0 x1 y1 orient status),
# blockages.txt (x0 y0 x1 y1 soft|hard) and, with insts=1, insts.txt
# (name master x y w h status, every non-macro instance).
proc od_dump { dir {insts 1} } {
  file mkdir $dir
  set blk [ord::get_db_block]
  set fh [open [file join $dir summary.txt] w]
  set die [$blk getDieArea]
  set core [$blk getCoreArea]
  puts $fh "dbu [[ord::get_db_tech] getDbUnitsPerMicron]"
  puts $fh "die [$die xMin] [$die yMin] [$die xMax] [$die yMax]"
  puts $fh "core [$core xMin] [$core yMin] [$core xMax] [$core yMax]"
  puts $fh "insts [llength [$blk getInsts]] nets [llength [$blk getNets]] rows [llength [$blk getRows]] blockages [llength [$blk getBlockages]]"
  close $fh
  set fh [open [file join $dir rows.txt] w]
  foreach r [$blk getRows] { set b [$r getBBox]; puts $fh "[$b xMin] [$b yMin] [$b xMax] [$b yMax] [$r getSiteCount]" }
  close $fh
  set fh [open [file join $dir macros.txt] w]
  set nm 0
  foreach i [$blk getInsts] {
    set m [$i getMaster]
    if { [$m isBlock] } {
      set b [$i getBBox]
      puts $fh "[$i getName] [$m getName] [$b xMin] [$b yMin] [$b xMax] [$b yMax] [$i getOrient] [$i getPlacementStatus]"
      incr nm
    }
  }
  close $fh
  set fh [open [file join $dir blockages.txt] w]
  foreach bl [$blk getBlockages] { set b [$bl getBBox]; puts $fh "[$b xMin] [$b yMin] [$b xMax] [$b yMax] [expr { [$bl isSoft] ? "soft" : "hard" }]" }
  close $fh
  set ni 0
  if { $insts } {
    set fh [open [file join $dir insts.txt] w]
    foreach i [$blk getInsts] {
      set m [$i getMaster]
      if { [$m isBlock] } { continue }
      lassign [$i getLocation] x y
      puts $fh "[$i getName] [$m getName] $x $y [$m getWidth] [$m getHeight] [$i getPlacementStatus]"
      incr ni
    }
    close $fh
  }
  return [od_jobj [list dir [od_jstr $dir] macros $nm insts $ni rows [llength [$blk getRows]]]]
}

# ---- Timing (needs liberty) --------------------------------------------------

proc od_wns {} {
  od_require_timing
  set path [lindex [find_timing_paths -path_delay max -sort_by_slack -group_path_count 1] 0]
  if { $path eq "" } { return [od_jobj [list wns null]] }
  return [od_jobj [list wns [od_jnum [get_property $path slack]] \
    from [od_jstr [get_full_name [get_property $path startpoint]]] \
    to [od_jstr [get_full_name [get_property $path endpoint]]]]]
}

proc od_worst_paths { {count 10} } {
  od_require_timing
  set items {}
  set paths [find_timing_paths -path_delay max -sort_by_slack -group_path_count $count]
  foreach p [lrange $paths 0 [expr { $count - 1 }]] {
    lappend items [od_jobj [list slack [od_jnum [get_property $p slack]] \
      from [od_jstr [get_full_name [get_property $p startpoint]]] \
      to [od_jstr [get_full_name [get_property $p endpoint]]]]]
  }
  return [od_jarr $items]
}

# Run a command and return what it printed through OpenROAD's logger: the
# report_* family, check_placement -verbose, anything that reports.
proc od_capture { script } {
  utl::redirectStringBegin
  set rc [catch { uplevel #0 $script } msg]
  set out [utl::redirectStringEnd]
  if { $rc } { error "$msg\n$out" }
  return $out
}

# ---- Socket server -----------------------------------------------------------

# Evaluate one request, capturing puts to stdout.
proc od_eval_capture { code } {
  set ::od_stdout ""
  rename ::puts ::od_puts_real
  proc ::puts { args } {
    set n [llength $args]
    set to_stdout [expr { $n == 1 || ($n == 2 && [lindex $args 0] eq "-nonewline") \
      || ($n == 2 && [lindex $args 0] eq "stdout") || ($n == 3 && [lindex $args 1] eq "stdout") }]
    if { $to_stdout } {
      append ::od_stdout [lindex $args end]
      if { [lindex $args 0] ne "-nonewline" } { append ::od_stdout "\n" }
      return
    }
    ::od_puts_real {*}$args
  }
  set rc [catch { uplevel #0 $code } result]
  rename ::puts ""
  rename ::od_puts_real ::puts
  return [list $rc $result $::od_stdout]
}

proc od_readable { chan } {
  if { [gets $chan line] < 0 } {
    if { [eof $chan] } { catch { close $chan } }
    return
  }
  set ::od_last_request [clock seconds]
  set t0 [clock milliseconds]
  if { [catch { binary decode base64 [string trim $line] } bytes] } {
    puts $chan [od_jobj [list ok false error [od_jstr "request is not base64"] stdout [od_jstr ""] ms 0]]
    flush $chan
    return
  }
  set code [encoding convertfrom utf-8 $bytes]
  lassign [od_eval_capture $code] rc result out
  set ms [expr { [clock milliseconds] - $t0 }]
  if { $rc } {
    puts $chan [od_jobj [list ok false error [od_jstr $result] stdout [od_jstr $out] ms $ms]]
  } else {
    puts $chan [od_jobj [list ok true result [od_jstr $result] stdout [od_jstr $out] ms $ms]]
  }
  flush $chan
}

proc od_accept { chan addr port } {
  fconfigure $chan -buffering line -blocking 1 -encoding utf-8
  fileevent $chan readable [list od_readable $chan]
}

# Provenance: the workspace and commit this daemon serves, when known. A
# daemon left over from an earlier session happily serves a stale ODB;
# check these against the commit under study before trusting a number.
set ::od_workspace [expr { [info exists ::env(BUILD_WORKSPACE_DIRECTORY)] ? $::env(BUILD_WORKSPACE_DIRECTORY) : "" }]
set ::od_commit ""
if { $::od_workspace ne "" } {
  catch { set ::od_commit [string trim [exec git -C $::od_workspace rev-parse HEAD]] }
}

set od_port [expr { [info exists ::env(ODB_DEBUG_PORT)] ? $::env(ODB_DEBUG_PORT) : 0 }]
set od_server [socket -server od_accept -myaddr 127.0.0.1 $od_port]
set od_port [lindex [fconfigure $od_server -sockname] 2]

set od_info_path [file join $::env(ODB_DEBUG_DIR) daemon.json]
set fh [open $od_info_path w]
puts $fh [od_jobj [list port $od_port pid [pid] dir [od_jstr $::env(ODB_DEBUG_DIR)] \
  design [od_jstr [[ord::get_db_block] getName]] \
  odb [od_jstr [expr { [info exists ::env(ODB_FILE)] ? $::env(ODB_FILE) : "" }]] \
  workspace [od_jstr $::od_workspace] commit [od_jstr $::od_commit] timing [od_jbool $::od_timing]]]
close $fh
puts "odb-debug: daemon listening on 127.0.0.1:$od_port (info: $od_info_path)"
puts "odb-debug: design [[ord::get_db_block] getName], [llength [[ord::get_db_block] getInsts]] insts, loaded in $::od_load_secs s, timing [expr { $::od_timing ? "on" : "off" }]"

# Idle exit: give the memory back when nobody asks. Default twice the load
# time, at least two minutes; ODB_DEBUG_IDLE_SECS overrides, 0 disables.
set ::od_last_request [clock seconds]
set ::od_idle [expr { [info exists ::env(ODB_DEBUG_IDLE_SECS)] ? int($::env(ODB_DEBUG_IDLE_SECS)) : max(120, int(2 * $::od_load_secs)) }]
proc od_idle_check {} {
  if { $::od_idle > 0 && [clock seconds] - $::od_last_request > $::od_idle } {
    puts "odb-debug: idle for $::od_idle s, exiting"
    catch { file delete $::od_info_path }
    exit 0
  }
  after 10000 od_idle_check
}
after 10000 od_idle_check
vwait forever
