# Shared by part.tcl, top.tcl and flat.tcl: the liberty, the clocks and the
# reg2reg endpoint report, so the three agree on what they time.
#
#   PSTA_LIBS    liberty files, space separated
#   PSTA_CLOCKS  "<port> <period> ...": an ideal clock on each port named,
#                period in picoseconds; nothing else is
#                constrained, so every timed path starts at a register
#                (or, in top.tcl, at an annotated side input whose arrival
#                came from one)

set ::psta_t0 [clock milliseconds]

# Wall seconds since the script started, and this process's peak resident
# memory in MiB (Linux), for the statistics.
proc psta_seconds {} { expr { ([clock milliseconds] - $::psta_t0) / 1000.0 } }
proc psta_peak_mib {} {
  if { [catch { open /proc/self/status } fh] } { return 0 }
  set kib 0
  while { [gets $fh line] >= 0 } {
    if { [regexp {^VmHWM:\s+(\d+)} $line -> kib] } { break }
  }
  close $fh
  return [expr { $kib / 1024 }]
}

# A one-line JSON object of `d`, a dict of numbers and strings.
proc psta_json { d } {
  set parts {}
  dict for {k v} $d {
    if { [string is double -strict $v] } {
      lappend parts "\"$k\": $v"
    } else {
      lappend parts "\"$k\": \"[string map {\\ \\\\ \" \\\"} $v]\""
    }
  }
  return "{[join $parts {, }]}"
}

proc psta_read_libs {} {
  foreach lib $::env(PSTA_LIBS) { read_liberty $lib }
  # OpenSTA takes its units from the first liberty it reads, and the
  # files come in no meaningful order (a macro's in ns, the cells' in
  # ps): PSTA_CLOCKS and every slack written are in picoseconds
  set_cmd_units -time ps
}

# One ideal clock per named port the linked design has; returns how many.
proc psta_clocks {} {
  set n 0
  foreach {port period} $::env(PSTA_CLOCKS) {
    set p [get_ports -quiet $port]
    if { [llength $p] } {
      create_clock -name $port -period $period $p
      incr n
    }
  }
  # a module whose ports were renamed (a folded entry cell's in0, in1, ...)
  # has none of the names: the clock is on the ports that reach its
  # registers' clock pins, with the one period
  if { !$n && [llength $::env(PSTA_CLOCKS)] == 2 && [llength [all_registers]] } {
    # the clock pins' nets, and back through the clock buffers and gates
    # that drive them, to the ports they start at
    set ports [dict create]
    set todo [get_nets -quiet -of_objects [all_registers -clock_pins]]
    set seen [dict create]
    while { [llength $todo] } {
      set net [lindex $todo end]
      set todo [lrange $todo 0 end-1]
      if { $net eq "NULL" } { continue }
      set nn [get_full_name $net]
      if { [dict exists $seen $nn] } { continue }
      dict set seen $nn 1
      if { [llength [get_ports -quiet $nn]] } {
        dict set ports $nn 1
        continue
      }
      foreach drv [get_pins -quiet -of_objects $net -filter "direction == output"] {
        foreach in [get_pins -quiet -of_objects [get_cells -of_objects $drv] -filter "direction == input"] {
          lappend todo [get_nets -quiet -of_objects $in]
        }
      }
    }
    set ports [dict keys $ports]
    if { [llength $ports] } {
      create_clock -name [lindex $::env(PSTA_CLOCKS) 0] -period [lindex $::env(PSTA_CLOCKS) 1] [get_ports $ports]
      incr n
    }
  }
  return $n
}

# Every register data pin with a constrained setup slack, as
# "<pin> <slack>" lines sorted by pin name, written to `file`. `skip` is a
# dict of pin names left out. Returns the count written.
proc psta_endpoints { file skip } {
  set lines {}
  foreach pin [all_registers -data_pins] {
    if { [dict exists $skip [get_full_name $pin]] } { continue }
    set s [get_property $pin slack_max]
    if { $s eq "INF" || $s eq "-INF" || $s eq "" } { continue }
    lappend lines "[get_full_name $pin] $s"
  }
  set lines [lsort $lines]
  set f [open $file w]
  if { [llength $lines] } { puts $f [join $lines "\n"] }
  close $f
  return [llength $lines]
}
