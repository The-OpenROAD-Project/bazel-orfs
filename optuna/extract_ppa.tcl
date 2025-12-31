source $::env(SCRIPTS_DIR)/load.tcl
# from optuna/results/asap7/mock_cpu/base/3_place.odb, we want 3_place
# stracted from $::env(ODB_FILE)
set file_stem [file rootname [file tail $::env(ODB_FILE)]]
load_design ${file_stem}.odb ${file_stem}.sdc

# ============================================================
# Performance Metrics
# ============================================================
set clocks [get_clocks]
set clock [lindex $clocks 0]
set clock_period [get_property $clock period]

set paths [find_timing_paths -path_group reg2reg -sort_by_slack -group_path_count 1]
set path [lindex $paths 0]
set slack [get_property $path slack]

# Calculate actual achievable clock period
set achievable_period [expr {$clock_period - $slack}]
set frequency_ghz [expr {1000.0 / $achievable_period}]

# ============================================================
# Area Metrics
# ============================================================
set db [::ord::get_db]
set chip [$db getChip]
set block [$chip getBlock]

# Get die area bbox
set die_bbox [$block getDieArea]
set die_width [expr {[$die_bbox xMax] - [$die_bbox xMin]}]
set die_height [expr {[$die_bbox yMax] - [$die_bbox yMin]}]
set die_area [expr {$die_width * $die_height}]
set die_area_um2 [expr {$die_area / 1000000.0}]

# Get core area bbox
set core_bbox [$block getCoreArea]
set core_width [expr {[$core_bbox xMax] - [$core_bbox xMin]}]
set core_height [expr {[$core_bbox yMax] - [$core_bbox yMin]}]
set core_area [expr {$core_width * $core_height}]
set core_area_um2 [expr {$core_area / 1000000.0}]

# Get cell area - sum of all instance areas
set total_cell_area 0
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    if {![$master isBlock]} {
        set inst_width [$master getWidth]
        set inst_height [$master getHeight]
        set inst_area [expr {$inst_width * $inst_height}]
        set total_cell_area [expr {$total_cell_area + $inst_area}]
    }
}
set cell_area_um2 [expr {$total_cell_area / 1000000.0}]

# Calculate utilization
if {$core_area_um2 > 0} {
    set utilization [expr {$cell_area_um2 / $core_area_um2 * 100.0}]
} else {
    set utilization 0.0
}

# ============================================================
# Power Metrics (basic estimate)
# ============================================================
set num_cells 0
set num_sequential 0
foreach inst [$block getInsts] {
    incr num_cells
    set master [$inst getMaster]
    if {[$master isSequential]} {
        incr num_sequential
    }
}
set num_nets [llength [$block getNets]]

# Rough power estimate:
# Sequential cells (flip-flops) consume more power due to switching
# Assume: FF ~2uW, combo logic ~0.5uW at this frequency
set estimated_power_uw [expr {$num_sequential * 2.0 + ($num_cells - $num_sequential) * 0.5}]

# ============================================================
# Output Results
# ============================================================
set fp [open $::env(OUTFILE) w]
puts $fp "# Performance Metrics"
puts $fp "clock_period: $clock_period"
puts $fp "slack: $slack"
puts $fp "achievable_period: $achievable_period"
puts $fp "frequency_ghz: $frequency_ghz"
puts $fp ""
puts $fp "# Area Metrics (um^2)"
puts $fp "die_area: $die_area_um2"
puts $fp "core_area: $core_area_um2"
puts $fp "cell_area: $cell_area_um2"
puts $fp "utilization: $utilization"
puts $fp ""
puts $fp "# Power Metrics (estimated)"
puts $fp "num_cells: $num_cells"
puts $fp "num_sequential: $num_sequential"
puts $fp "num_nets: $num_nets"
puts $fp "estimated_power_uw: $estimated_power_uw"
close $fp
