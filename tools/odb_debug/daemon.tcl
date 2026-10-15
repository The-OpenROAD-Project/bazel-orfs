# odb-debug daemon: a persistent OpenROAD session on a stage ODB, served by
# OpenROAD's web viewer on localhost, so a person or an agent can ask a
# placed or routed design questions without paying the ODB and liberty load
# for each, step through a tool's debug renderer and draw it headless.
#
# Run it as a flow stage's companion so it gets the flow's exact environment
# (ODB, SDC, liberty set, RC, derates), either through bazel
#
#   bazelisk run //my:design_place_odb_debug -- ODB_DEBUG_DIR=tmp/odb-debug
#
# or from a tree deployed by `bazelisk run //:deps -- start <flow> <stage>`, where the checkpoint of an unfinished or
# failed stage can be dropped into results/ and opened directly:
#
#   ./make run RUN_SCRIPT=$PWD/tools/odb_debug/daemon.tcl \
#       ODB_FILE=<results>/3_4_place_resized.odb ODB_DEBUG_DIR=$PWD/tmp/odb-debug
#
# Under bazel run a relative ODB_DEBUG_DIR is relative to where it was
# invoked. A deployed tree's make runs from inside the tree, so give that
# one an absolute directory.
#
# GUI_TIMING=0 skips the liberty files: a 2.5 GB, 1.35 M-instance ODB then
# loads in seconds and a few GB, and every geometry query works; the timing
# queries answer that no timing is loaded. Without it the design's liberty
# set loads and the timing queries work too.
#
# Requests: `od_web_request <base64 of UTF-8 Tcl>` through the viewer's
# tcl_eval (odbdebug.py does this); the reply is one JSON object,
#   {"ok":true,"result":"<string>","stdout":"<string>","ms":<int>}
#   {"ok":false,"error":"<message>","stdout":"<string>","ms":<int>}
# The od_* procs return JSON strings, so a client decodes .result. Anything
# else is fair game; the session has the trust model of an interactive
# `openroad` shell on the same machine. It listens on 127.0.0.1 only, and a
# browser on that address is the GUI.
#
# Files, all under ODB_DEBUG_DIR (required): daemon.json, written before the
# viewer starts -- port, pid, url, design, odb, workspace, commit, timing --
# and removed when the daemon exits on its own; heartbeat, for the idle
# exit. ODB_DEBUG_IDLE_SECS is the
# idle time before it exits (0 disables; default twice the load time, at
# least 120 s), so a forgotten daemon gives its memory back.

set ::od_t0 [clock milliseconds]

if { ![info exists ::env(ODB_DEBUG_DIR)] || $::env(ODB_DEBUG_DIR) eq "" } {
  error "ODB_DEBUG_DIR must be set, e.g. ODB_DEBUG_DIR=tmp/odb-debug"
}
# bazel run starts this from the runfiles tree; a relative directory means
# one relative to where bazel run was invoked, not a directory in the tree.
if {
  [file pathtype $::env(ODB_DEBUG_DIR)] ne "absolute"
  && [info exists ::env(BUILD_WORKING_DIRECTORY)]
  && $::env(BUILD_WORKING_DIRECTORY) ne ""
} {
  set ::env(ODB_DEBUG_DIR) [file join $::env(BUILD_WORKING_DIRECTORY) $::env(ODB_DEBUG_DIR)]
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

# check_setup -verbose without the pin lists in the reply: each warning
# with its count, the first `examples` pins and the `top` most common
# module paths `depth` levels deep, so 100k unclocked pins come back as
# the few modules they sit in. Hierarchy is split at "/" and at the "."
# of a flattened yosys name; a port is grouped by its bus name. Up to
# `classify` unconstrained endpoints are sorted by whether every
# startpoint in their fan-in is an input port: what an SDC without
# set_input_delay leaves unconstrained by design. `out`, when given,
# gets every line. What each warning means:
# .claude/commands/check-setup.md.
proc od_check_setup { {examples 10} {depth 3} {top 20} {out ""} {classify 200} } {
  od_require_timing
  # no_input_delay no_output_delay multiple_clock no_clock unconstrained
  # loops generated_clocks: everything, as a bare check_setup does
  set errors [sta::check_timing_cmd 1 1 1 1 1 1 1]
  if { $out ne "" } {
    set fh [open $out w]
    foreach error $errors { puts $fh [join $error "\n  "] }
    close $fh
  }
  set items {}
  foreach error $errors {
    set msg [lindex $error 0]
    set objs {}
    foreach obj [lrange $error 1 end] {
      if { [string match "|*" $obj] || [string match "---*" $obj] } { continue }
      lappend objs $obj
    }
    set count [llength $objs]
    regexp {There (?:is|are) (\d+) } $msg -> count
    set prefixes [dict create]
    foreach obj $objs {
      dict incr prefixes [od_module_path $obj $depth]
    }
    set ranked [lsort -integer -decreasing -stride 2 -index 1 $prefixes]
    set prefix_items {}
    foreach {key n} [lrange $ranked 0 [expr { 2 * $top - 1 }]] {
      lappend prefix_items [od_jobj [list prefix [od_jstr $key] count $n]]
    }
    set example_items {}
    foreach obj [lrange $objs 0 [expr { $examples - 1 }]] {
      lappend example_items [od_jstr $obj]
    }
    set pairs [list \
      warning [od_jstr $msg] \
      count $count \
      prefixes [od_jarr $prefix_items] \
      examples [od_jarr $example_items]]
    if { [string match "*unconstrained endpoint*" $msg] && $classify > 0 } {
      lappend pairs inputs_only [od_inputs_only [lrange $objs 0 [expr { $classify - 1 }]]]
    }
    lappend items [od_jobj $pairs]
  }
  return [od_jarr $items]
}

# The module path of a pin `depth` levels deep: the instance's own name
# and the pin dropped. A port (no hierarchy) is its bus name.
proc od_module_path { obj depth } {
  set slash [string last / $obj]
  if { $slash < 0 } {
    return [regsub {\[\d+\]$} $obj {}]
  }
  set parts [split [string range $obj 0 [expr { $slash - 1 }]] /.]
  set parts [lrange $parts 0 end-1]
  if { $parts eq {} } { return "(top)" }
  return [join [lrange $parts 0 [expr { $depth - 1 }]] /]
}

# Of these endpoints, how many have only input ports as the startpoints
# of their fan-in, and how many have a register too.
proc od_inputs_only { endpoints } {
  set only 0
  set other {}
  foreach name $endpoints {
    set pin [get_pins -quiet $name]
    if { $pin eq "" } { set pin [get_ports -quiet $name] }
    if { $pin eq "" } { continue }
    set starts [get_fanin -to $pin -startpoints_only -flat]
    # a startpoint inside the design is an instance pin, "inst/pin"
    set reg 0
    foreach s $starts {
      if { [string first / [get_full_name $s]] >= 0 } { set reg 1; break }
    }
    if { $reg } { lappend other [od_jstr $name] } else { incr only }
  }
  return [od_jobj [list classified [llength $endpoints] inputs_only $only \
    with_register [llength $other] with_register_examples [od_jarr [lrange $other 0 9]]]]
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

# ---- Requests ----------------------------------------------------------------

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

# The idle watchdog reads this: "busy <t>" while a request runs, "idle <t>"
# from when it ended, so a request longer than the idle time is neither
# cut short nor followed by an exit the moment it returns.
proc od_heartbeat { state } {
  set tmp $::od_heartbeat_path.tmp
  set f [open $tmp w]
  puts $f "$state [clock seconds]"
  close $f
  file rename -force $tmp $::od_heartbeat_path
}

# One request: base64 of UTF-8 Tcl, evaluated at global scope; the reply
# is one JSON object,
#   {"ok":true,"result":"<string>","stdout":"<string>","ms":<int>}
#   {"ok":false,"error":"<message>","stdout":"<string>","ms":<int>}
# The client sends `od_web_request <base64>` through the viewer's
# tcl_eval and decodes the result.
proc od_web_request { b64 } {
  od_heartbeat busy
  set t0 [clock milliseconds]
  if { [catch { binary decode base64 [string trim $b64] } bytes] } {
    od_heartbeat idle
    return [od_jobj [list ok false error [od_jstr "request is not base64"] stdout [od_jstr ""] ms 0]]
  }
  set code [encoding convertfrom utf-8 $bytes]
  lassign [od_eval_capture $code] rc result out
  set ms [expr { [clock milliseconds] - $t0 }]
  od_heartbeat idle
  if { $rc } {
    return [od_jobj [list ok false error [od_jstr $result] stdout [od_jstr $out] ms $ms]]
  }
  return [od_jobj [list ok true result [od_jstr $result] stdout [od_jstr $out] ms $ms]]
}

# ---- Serving -----------------------------------------------------------------

# Provenance: the workspace and commit this daemon serves, when known. A
# daemon left over from an earlier session happily serves a stale ODB;
# check these against the commit under study before trusting a number.
set ::od_workspace [expr { [info exists ::env(BUILD_WORKSPACE_DIRECTORY)] ? $::env(BUILD_WORKSPACE_DIRECTORY) : "" }]
set ::od_commit ""
if { $::od_workspace ne "" } {
  catch { set ::od_commit [string trim [exec git -C $::od_workspace rev-parse HEAD]] }
}

# web_server takes a port, not a listening socket: find a free one.
set od_port [expr { [info exists ::env(ODB_DEBUG_PORT)] ? $::env(ODB_DEBUG_PORT) : 0 }]
if { $od_port == 0 } {
  set probe [socket -server {apply {{c a p} {close $c}}} -myaddr 127.0.0.1 0]
  set od_port [lindex [fconfigure $probe -sockname] 2]
  close $probe
}

set ::od_heartbeat_path [file join $::env(ODB_DEBUG_DIR) heartbeat]
od_heartbeat idle

# daemon.json is the client's signal to connect, so it appears only once
# the viewer takes requests (see the end of this file); until then it is
# daemon.json.pending.
set ::od_info_path [file join $::env(ODB_DEBUG_DIR) daemon.json]
set od_pending $::od_info_path.pending
catch { file delete $::od_info_path }
set fh [open $od_pending w]
puts $fh [od_jobj [list port $od_port pid [pid] dir [od_jstr $::env(ODB_DEBUG_DIR)] \
  url [od_jstr "http://127.0.0.1:$od_port"] \
  design [od_jstr [[ord::get_db_block] getName]] \
  odb [od_jstr [expr { [info exists ::env(ODB_FILE)] ? $::env(ODB_FILE) : "" }]] \
  workspace [od_jstr $::od_workspace] commit [od_jstr $::od_commit] timing [od_jbool $::od_timing]]]
close $fh
puts "odb-debug: daemon on http://127.0.0.1:$od_port (info: $::od_info_path)"
puts "odb-debug: design [[ord::get_db_block] getName], [llength [[ord::get_db_block] getInsts]] insts, loaded in $::od_load_secs s, timing [expr { $::od_timing ? "on" : "off" }]"

# Idle exit: give the memory back when nobody asks. Default twice the load
# time, at least two minutes; ODB_DEBUG_IDLE_SECS overrides, 0 disables.
# web_server blocks and Tcl's event loop does not run under it, so a timer
# here would never fire: a shell beside the daemon watches the heartbeat
# and stops it. Requests typed in a browser bypass the heartbeat; browse
# with ODB_DEBUG_IDLE_SECS=0. It stops it as a browser's `exit` does,
# through the viewer with the client beside this script: web_server
# returns and the daemon exits 0 below. A kill would end it with
# SIGTERM, which make reports as a failed run.
set od_client [file join [file dirname [file normalize [info script]]] odbdebug.py]
if { ![file exists $od_client] } {
  error "odb-debug: $od_client is missing beside daemon.tcl; the idle exit stops the daemon through it"
}
set ::od_idle [expr { [info exists ::env(ODB_DEBUG_IDLE_SECS)] ? int($::env(ODB_DEBUG_IDLE_SECS)) : max(120, int(2 * $::od_load_secs)) }]
if { $::od_idle > 0 } {
  set od_poll [expr { max(1, min(10, $::od_idle / 2)) }]
  set od_watchdog {
    pid=$1 heartbeat=$2 idle=$3 info=$4 poll=$5 python=$6 client=$7 dir=$8
    # This shell holds openroad's stdout, the pipe its parent tees, so the
    # parent reaps openroad only once this shell has exited too: an exited
    # openroad is a zombie until then, and kill -0 still finds a zombie.
    alive() {
      state=$(ps -o stat= -p "$pid" 2>/dev/null) && [ "${state#Z}" = "$state" ]
    }
    while alive; do
      sleep "$poll"
      read state since < "$heartbeat" || continue
      if [ "$state" = idle ] && [ $(( $(date +%s) - since )) -gt "$idle" ]; then
        echo "odb-debug: idle for $idle s, exiting"
        # openroad exits inside web_server and never reaches the delete
        # below it, so the request deletes daemon.json first: the client
        # has read the port from it by then. Its reply is the viewer
        # closing, so its output only matters when that fails.
        out=$("$python" "$client" "$dir" --tcl "file delete {$info}; exit" 2>&1)
        for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
          alive || exit 0
          sleep 0.5
        done
        echo "odb-debug: the daemon did not exit through the viewer; killing it"
        printf '%s\n' "$out" | tail -n 5
        grep -q "\"pid\":$pid," "$info" && rm -f "$info"
        kill "$pid"
        exit 1
      fi
    done
  }
  exec sh -c $od_watchdog odb-debug-watchdog [pid] $::od_heartbeat_path $::od_idle $::od_info_path $od_poll \
    $::env(PYTHON_EXE) $od_client $::env(ODB_DEBUG_DIR) >@ stdout 2>@ stderr &
}

# A debug pause inside tcl_eval holds the thread serving it; with one
# thread nothing is left to deliver the continue.
if { [thread_count] < 2 } {
  puts "odb-debug: raising threads from [thread_count] to 2 for the web viewer"
  set_thread_count 2
}
# web_server listens, then runs the browser launcher (skipped here with
# -no_browser, patch 0126), then lets requests in; a request
# that arrives in between crashes OpenROAD (signal 11). It blocks, so the
# rename that tells clients to connect happens beside it, after a grace.
exec sh -c {sleep 2; [ -f "$1" ] && mv -f "$1" "$2"} odb-debug-ready \
  $od_pending $::od_info_path >@ stdout 2>@ stderr &
web_server -no_browser -port $od_port -bind 127.0.0.1
catch { file delete $::od_info_path }
exit 0
