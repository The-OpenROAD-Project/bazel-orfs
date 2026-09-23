# Boundary probe, structural half. Run on a synthesis ODB written with
# OPENROAD_HIERARCHICAL=1, so the kept modules are dbModInsts with their
# boundary terminals. For every module instance: how many boundary pins it
# has in each direction, how many of them are registered right at the
# boundary (an input whose every load inside is a register pin; an output
# whose driver inside is a register), the cells and flops directly inside,
# and how many register outputs inside drive nothing but register inputs
# (an empty pipeline stage: the slack retiming would move into logic).
# One line per module instance to PROBE_OUT.
# Follow a net through buffers and inverters (single-input, single-output
# cells; the QN of an asap7 flop always has one) for up to `depth` levels
# and report whether every load at the end is a register pin. Returns
# {any all_seq}: whether anything was reached and whether all of it was
# sequential.
# asap7 buffers and inverters by name; odb masters carry no such flag.
proc probe_bufinv { master } {
  return [regexp {^(BUF|INV|HB)} [$master getName]]
}

proc probe_loads_seq { net depth } {
  set any 0
  set all 1
  foreach lt [$net getITerms] {
    if { [$lt getIoType] eq "OUTPUT" } { continue }
    set inst [$lt getInst]
    set m [$inst getMaster]
    if { [$m isSequential] } { set any 1; continue }
    if { $depth > 0 && [probe_bufinv $m] } {
      foreach ot [$inst getITerms] {
        if { [$ot getIoType] ne "OUTPUT" } { continue }
        set onet [$ot getNet]
        if { $onet eq "NULL" } { continue }
        lassign [probe_loads_seq $onet [expr { $depth - 1 }]] a s
        if { $a } { set any 1 }
        if { !$s } { set all 0 }
      }
      continue
    }
    set any 1
    set all 0
  }
  return [list $any $all]
}

set block [ord::get_db_block]
set out [open $::env(PROBE_OUT) w]
set n 0
foreach mi [$block getModInsts] {
  set mod [$mi getMaster]
  set name [$mi getHierarchicalName]
  set nin 0
  set nout 0
  set rin 0
  set rout 0
  foreach mbt [$mod getModBTerms] {
    set io [$mbt getIoType]
    set mnet [$mbt getModNet]
    if { $mnet eq "NULL" } { continue }
    lassign [probe_loads_seq $mnet 3] has_load loads_seq
    set driver_seq 0
    foreach it [$mnet getITerms] {
      if { [$it getIoType] ne "OUTPUT" } { continue }
      set inst [$it getInst]
      set m [$inst getMaster]
      if { [$m isSequential] } { set driver_seq 1; break }
      # a buffered or inverted register output
      if { [probe_bufinv $m] } {
        foreach dt [$inst getITerms] {
          if { [$dt getIoType] ne "INPUT" } { continue }
          set dnet [$dt getNet]
          if { $dnet eq "NULL" } { continue }
          foreach ut [$dnet getITerms] {
            if { [$ut getIoType] eq "OUTPUT" && [[[$ut getInst] getMaster] isSequential] } { set driver_seq 1 }
          }
        }
      }
    }
    if { $io eq "INPUT" } {
      incr nin
      if { $has_load && $loads_seq } { incr rin }
    } elseif { $io eq "OUTPUT" } {
      incr nout
      if { $driver_seq } { incr rout }
    }
  }
  set cells 0
  set flops 0
  set empty_stages 0
  foreach inst [$mod getInsts] {
    incr cells
    set m [$inst getMaster]
    if { ![$m isSequential] } { continue }
    incr flops
    foreach it [$inst getITerms] {
      if { [$it getIoType] ne "OUTPUT" } { continue }
      set net [$it getNet]
      if { $net eq "NULL" } { continue }
      lassign [probe_loads_seq $net 3] any all_seq
      if { $any && $all_seq } { incr empty_stages }
    }
  }
  puts $out "module $name master [$mod getName] in $nin reg_in $rin out $nout reg_out $rout cells $cells flops $flops empty_stages $empty_stages"
  incr n
}
close $out
puts "boundaries: $n module instances written to $::env(PROBE_OUT)"
