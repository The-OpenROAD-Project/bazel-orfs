# Extract timing, area, cell/VT mix, ADDED-cell adoption, wirelength and power
# from either 1_synth.odb or 5_1_grt.odb into a single JSON file.
source $::env(SCRIPTS_DIR)/load.tcl

set stage_stem $::env(STAGE_STEM)
load_design ${stage_stem}.odb

if { [string match "5_*" $stage_stem] || [string match "6_*" $stage_stem] } {
  set_propagated_clock [all_clocks]
  estimate_parasitics -global_routing
} elseif { [string match "4_*" $stage_stem] } {
  set_propagated_clock [all_clocks]
  estimate_parasitics -placement
} elseif { ![string match "1_*" $stage_stem] } {
  estimate_parasitics -placement
}

set added_stems {
  AO21BBx1 AO21BBx2 AO21BBx4
  AO21Bx1 AO21Bx2 AO21Bx4 AO21Bx6
  AO22BBx1 AO22BBx2
  AOI21x2 AOI21x4 AOI21x4_1 AOI21x6
  AOI22x2
  INVx12
  MAJx1
  MUX2Ix1 MUX2x1 MUX2x3
  NAND2Bx1 NAND2Bx2 NAND2Bx2_1 NAND2Bx3 NAND2Bx4 NAND2Bx4_1
  NAND2x3 NAND2x4 NAND2x6
  NAND3BBx1 NAND3BBx1_1 NAND3BBx4
  NAND3Bx1 NAND3Bx1_1 NAND3Bx6
  NAND3x4
  NAND4Bx1 NAND4x4
  NOR2Bx1 NOR2Bx1_1 NOR2Bx2 NOR2Bx2_1 NOR2Bx3 NOR2Bx4 NOR2Bx6
  NOR2x4 NOR2x6
  NOR3BBx1 NOR3BBx1_1
  NOR3Bx1 NOR3Bx1_1 NOR3Bx3 NOR3Bx4 NOR3Bx4_1
  NOR3x4 NOR3x8
  OA21BBx1 OA21BBx2
  OA21Bx1 OA21Bx2 OA21Bx4
  OA22BBx1
  OAI211x1 OAI21x2 OAI21x4
}
set added_dict [dict create]
foreach s $added_stems {
  foreach vt {R L SL SRAM} {
    if { [regexp {^(.+)(_1)$} $s -> base suf] } {
      dict set added_dict "${base}_ASAP7_75t_${vt}${suf}" $s
      dict set added_dict "${s}_ASAP7_75t_${vt}" $s
    } else {
      dict set added_dict "${s}_ASAP7_75t_${vt}" $s
    }
  }
}

set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set dbu2 [expr { double($dbu) * $dbu }]

set by_master [dict create]
foreach inst [$block getInsts] {
  dict incr by_master [[$inst getMaster] getName]
}

set stdcell_area 0.0
set stdcell_count 0
set buf_count 0
set inv_count 0
set added_count 0
set added_area 0.0
set vt_counts [dict create R 0 L 0 SL 0 other 0]
set vt_areas [dict create R 0.0 L 0.0 SL 0.0 other 0.0]
set added_by_stem [dict create]

foreach {name count} $by_master {
  set master [[ord::get_db] findMaster $name]
  if { [$master isBlock] || [$master isFiller] } { continue }
  set mtype [$master getType]
  if { [string match "CORE_SPACER" $mtype] || [string match "CORE_WELLTAP" $mtype] \
      || [string match "CORE_ANTENNACELL" $mtype] || [string match "ENDCAP*" $mtype] \
      || [string match "TIE*" $name] } {
    continue
  }
  set cell_area [expr { [$master getWidth] * [$master getHeight] / $dbu2 * $count }]
  set stdcell_area [expr { $stdcell_area + $cell_area }]
  incr stdcell_count $count

  if { [string match "BUF*" $name] || [string match "CLKBUF*" $name] } {
    incr buf_count $count
  } elseif { [string match "INV*" $name] } {
    incr inv_count $count
  }

  set vt_key "other"
  if { [regexp {_ASAP7_75t_(SL|L|R)($|_)} $name -> vt_tag] } {
    set vt_key $vt_tag
  }
  dict incr vt_counts $vt_key $count
  dict set vt_areas $vt_key [expr { [dict get $vt_areas $vt_key] + $cell_area }]

  if { [dict exists $added_dict $name] } {
    set stem [dict get $added_dict $name]
    incr added_count $count
    set added_area [expr { $added_area + $cell_area }]
    if { [dict exists $added_by_stem $stem] } {
      dict incr added_by_stem $stem $count
    } else {
      dict set added_by_stem $stem $count
    }
  }
}

set flops [llength [all_registers -cells]]
set clk [lindex [all_clocks] 0]
set period_ps [get_property $clk period]

set r2r_wns 0.0
set r2r_paths [find_timing_paths -path_group reg2reg -sort_by_slack -group_path_count 1]
if { [llength $r2r_paths] > 0 } {
  set r2r_wns [get_property [lindex $r2r_paths 0] slack]
}
set achieved_period_ps [expr { $period_ps - $r2r_wns }]

set r2r_tns 0.0
set r2r_violating 0
set ends [find_timing_paths -path_group reg2reg -endpoint_path_count 1 \
  -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint]
foreach t $ends {
  set slk [get_property $t slack]
  if { $slk < 0.0 } {
    set r2r_tns [expr { $r2r_tns + $slk }]
    incr r2r_violating
  }
}
set r2r_endpoints [llength $ends]
unset ends

# Pure stdcell flop-to-flop min period (excluding hardened macro endpoints).
set flop_cells {}
foreach r [all_registers -cells] {
  set dbi [sta::sta_to_db_inst $r]
  if { $dbi ne "NULL" && $dbi ne "" && ![[$dbi getMaster] isBlock] } {
    lappend flop_cells $r
  }
}
set ff_min_period_ps $achieved_period_ps
if { [llength $flop_cells] > 0 } {
  set ff_paths [find_timing_paths -from $flop_cells -to $flop_cells -sort_by_slack -group_path_count 1]
  if { [llength $ff_paths] > 0 } {
    set ff_min_period_ps [expr { $period_ps - [get_property [lindex $ff_paths 0] slack] }]
  }
}

# Wirelength from routed guides if present.
set route_wl_um 0.0
foreach net [$block getNets] {
  set guides [$net getGuides]
  foreach g $guides {
    set box [$g getBox]
    set route_wl_um [expr { $route_wl_um + ([$box dx] + [$box dy]) / double($dbu) }]
  }
}

# Embed report_power -format json directly when past synthesis.
set pwr_json "{\"Total\": {\"internal\": 0.0, \"switching\": 0.0, \"leakage\": 0.0, \"total\": 0.0}}"
if { ![string match "1_*" $stage_stem] } {
  set pwr_tmp "$::env(OUT_JSON).power.tmp"
  report_power -format json > $pwr_tmp
  set pfh [open $pwr_tmp r]
  set raw_pwr [string trim [read $pfh]]
  close $pfh
  file delete -force $pwr_tmp
  set brace_idx [string first "\{" $raw_pwr]
  if { $brace_idx >= 0 } {
    set pwr_json [string range $raw_pwr $brace_idx end]
  }
}

set stem_pairs {}
dict for {stem cnt} $added_by_stem {
  lappend stem_pairs [list $stem $cnt]
}
set stem_pairs [lsort -integer -decreasing -index 1 $stem_pairs]
set stem_json {}
foreach pair $stem_pairs {
  lassign $pair s c
  lappend stem_json [format "\"%s\": %d" $s $c]
}

set fh [open $::env(OUT_JSON) w]
puts $fh "{"
puts $fh [format "  \"arm\": \"%s\"," $::env(ARM_NAME)]
puts $fh [format "  \"seed\": %d," $::env(SEED_NUM)]
puts $fh [format "  \"stage\": \"%s\"," $stage_stem]
puts $fh [format "  \"sdc_period_ps\": %.3f," $period_ps]
puts $fh [format "  \"reg2reg_wns_ps\": %.3f," $r2r_wns]
puts $fh [format "  \"reg2reg_min_period_ps\": %.3f," $achieved_period_ps]
puts $fh [format "  \"ff_only_min_period_ps\": %.3f," $ff_min_period_ps]
puts $fh [format "  \"reg2reg_tns_ns\": %.3f," [expr { $r2r_tns / 1000.0 }]]
puts $fh [format "  \"reg2reg_violating_endpoints\": %d," $r2r_violating]
puts $fh [format "  \"reg2reg_total_endpoints\": %d," $r2r_endpoints]
puts $fh [format "  \"stdcell_count\": %d," $stdcell_count]
puts $fh [format "  \"stdcell_area_um2\": %.3f," $stdcell_area]
puts $fh [format "  \"flops\": %d," $flops]
puts $fh [format "  \"buf_count\": %d," $buf_count]
puts $fh [format "  \"inv_count\": %d," $inv_count]
puts $fh [format "  \"added_cell_count\": %d," $added_count]
puts $fh [format "  \"added_cell_area_um2\": %.3f," $added_area]
puts $fh [format "  \"vt_counts\": {\"RVT\": %d, \"LVT\": %d, \"SLVT\": %d, \"other\": %d}," \
  [dict get $vt_counts R] [dict get $vt_counts L] [dict get $vt_counts SL] [dict get $vt_counts other]]
puts $fh [format "  \"vt_areas_um2\": {\"RVT\": %.3f, \"LVT\": %.3f, \"SLVT\": %.3f, \"other\": %.3f}," \
  [dict get $vt_areas R] [dict get $vt_areas L] [dict get $vt_areas SL] [dict get $vt_areas other]]
puts $fh [format "  \"guide_wl_um\": %.1f," $route_wl_um]
puts $fh "  \"report_power\": $pwr_json,"
puts $fh [format "  \"added_by_stem\": {%s}" [join $stem_json ", "]]
puts $fh "}"
close $fh
