# Peel probe: which of a hardened block's flops could move out into a
# wrapper the parent flattens, so the parent's placer puts them anywhere
# along the crossing. Run on a flat block's ODB (synth or place) through
# its odb_debug session, structure only (GUI_TIMING=0).
#
# A flop is peelable on its input side when its D pin is driven from an
# input port through at most buffers and inverters, and on its output
# side when its Q reaches an output port the same way. "pure" means the
# port or the Q reaches nothing else, so peeling adds no core pin;
# "shared" means it does (the port also feeds other logic, or Q also
# feeds the core), one new core pin per flop. One tab-separated line per
# flop to PEEL_OUT, columns `kind flop ports extra_pins da_ps`; the
# summary on stdout. With PEEL_TIMING=1 (a session with GUI_TIMING=1),
# da_ps is the period minus the slack at the flop's D: how long the
# block's own stage into the flop is, the half of the crossing a peeled
# flop shares. peel_bound.py reads the file.

proc peel_bufinv { master } {
  return [regexp {^(BUF|INV|HB)} [$master getName]]
}

# The input port an input net comes from through buffers and inverters,
# or "" when anything else drives it.
proc peel_port_of { net depth } {
  foreach bt [$net getBTerms] {
    if { [$bt getIoType] eq "INPUT" } { return [$bt getName] }
  }
  foreach it [$net getITerms] {
    if { [$it getIoType] ne "OUTPUT" } { continue }
    set inst [$it getInst]
    if { $depth <= 0 || ![peel_bufinv [$inst getMaster]] } { return "" }
    foreach i [$inst getITerms] {
      if { [$i getIoType] ne "INPUT" || [$i isInputSignal] == 0 } { continue }
      set n [$i getNet]
      if { $n eq "NULL" } { return "" }
      return [peel_port_of $n [expr { $depth - 1 }]]
    }
  }
  return ""
}

# Where a net goes through buffers and inverters: {ports flops other},
# the output port names, the count of register loads and the other
# loads' instances.
proc peel_loads { net depth } {
  set ports [list]
  set flops 0
  set other [list]
  foreach bt [$net getBTerms] {
    if { [$bt getIoType] eq "OUTPUT" } { lappend ports [$bt getName] }
  }
  foreach it [$net getITerms] {
    if { [$it getIoType] ne "INPUT" } { continue }
    set inst [$it getInst]
    set m [$inst getMaster]
    if { [$m isSequential] } { incr flops; continue }
    if { $depth > 0 && [peel_bufinv $m] } {
      foreach o [$inst getITerms] {
        if { [$o getIoType] ne "OUTPUT" } { continue }
        set n [$o getNet]
        if { $n eq "NULL" } { continue }
        lassign [peel_loads $n [expr { $depth - 1 }]] p f x
        set ports [concat $ports $p]
        incr flops $f
        set other [concat $other $x]
      }
      continue
    }
    lappend other $inst
  }
  return [list $ports $flops $other]
}

# Whether everything `inst` drives, through up to `depth` levels of
# logic, ends at `flop`'s D and nowhere else: the flop's own hold or
# enable mux, which moves out with it.
proc peel_self_only { inst flop depth } {
  foreach o [$inst getITerms] {
    if { [$o getIoType] ne "OUTPUT" } { continue }
    set n [$o getNet]
    if { $n eq "NULL" } { continue }
    if { [llength [$n getBTerms]] > 0 } { return 0 }
    foreach l [$n getITerms] {
      if { [$l getIoType] ne "INPUT" } { continue }
      set i [$l getInst]
      if { $i eq $flop } { continue }
      if { $depth <= 0 || [[$i getMaster] isSequential] } { return 0 }
      if { ![peel_self_only $i $flop [expr { $depth - 1 }]] } { return 0 }
    }
  }
  return 1
}

# The block's stage into `inst`: the period minus the slack at its D, in
# the library's time unit, or "" without timing. STA names are odb's
# with the escaped brackets unescaped; `?` matches either.
proc peel_da { inst period } {
  if { $period eq "" } { return "" }
  set g [string map {"\\\[" ? "\\\]" ?} [$inst getName]]
  set pins [get_pins -quiet "$g/D"]
  if { [llength $pins] != 1 } { return "" }
  set s [get_property $pins slack_max]
  if { ![string is double -strict $s] } { return "" }
  return [format %.0f [expr { $period - $s }]]
}

set period ""
if { [info exists ::env(PEEL_TIMING)] && $::env(PEEL_TIMING) } {
  set period [get_property [lindex [all_clocks] 0] period]
}
set block [ord::get_db_block]
set out [open $::env(PEEL_OUT) w]
puts $out "kind\tflop\tports\textra_pins\tda_ps"
set nflops 0
set in_pure 0
set in_shared 0
set out_pure 0
set out_shared 0
array set reg_out {}
array set reg_in {}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  if { ![$m isSequential] } { continue }
  incr nflops
  foreach it [$inst getITerms] {
    set mt [$it getMTerm]
    if { [$mt getSigType] ne "SIGNAL" } { continue }
    set net [$it getNet]
    if { $net eq "NULL" } { continue }
    set io [$it getIoType]
    if { $io eq "INPUT" && [$mt getName] eq "D" } {
      set port [peel_port_of $net 3]
      if { $port eq "" } { continue }
      set pnet [[$block findBTerm $port] getNet]
      lassign [peel_loads $pnet 3] p f x
      set x [llength $x]
      if { $f == 1 && $x == 0 } {
        incr in_pure
        puts $out "in_pure\t[$inst getName]\t$port\t0\t"
      } else {
        incr in_shared
        puts $out "in_shared\t[$inst getName]\t$port\t1\t"
      }
      set reg_in($port) 1
    } elseif { $io eq "OUTPUT" } {
      lassign [peel_loads $net 3] p f x
      if { [llength $p] == 0 } { continue }
      set real 0
      foreach l $x {
        if { ![peel_self_only $l $inst 3] } { incr real }
      }
      if { $f == 0 && $real == 0 } {
        incr out_pure
        puts $out "out_pure\t[$inst getName]\t[join $p ,]\t0\t[peel_da $inst $period]"
      } else {
        incr out_shared
        puts $out "out_shared\t[$inst getName]\t[join $p ,]\t1\t[peel_da $inst $period]"
      }
      foreach port $p { set reg_out($port) 1 }
    }
  }
}
set nin 0
set nout 0
foreach bt [$block getBTerms] {
  if { [$bt getSigType] ne "SIGNAL" } { continue }
  if { [$bt getIoType] eq "INPUT" } { incr nin } else { incr nout }
}
close $out
puts "peel: flops $nflops ports in $nin out $nout"
puts "peel: registered inputs [array size reg_in] of $nin, flops pure $in_pure shared $in_shared"
puts "peel: registered outputs [array size reg_out] of $nout, flops pure $out_pure shared $out_shared"
