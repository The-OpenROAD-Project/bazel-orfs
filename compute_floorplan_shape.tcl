source $::env(SCRIPTS_DIR)/load.tcl

# Floorplan-shape heuristic: emits CORE_UTILIZATION + CORE_MARGIN for the
# floorplan stage, computed from synth-stage area data. These two knobs
# together determine the die geometry the placer + repair_design will see;
# co-locating them keeps "how the floorplan is sized" in one place instead
# of split between a heuristic (utilization) and a static constant (margin).
#
# Used via orfs_arguments(...). Constants are read from environment with
# the values below as defaults; override per-design via the `arguments`
# attr on orfs_arguments.

load_design 1_synth.odb 1_synth.sdc

proc env_or_default { name default } {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

set block [ord::get_db_block]

# Sum standard-cell area (CORE* masters) and macro / fixed area separately.
# repair_design only adds std cells (buffers, resized gates), so the
# headroom budget is computed against std-cell area, not macro area.
set std_cell_area_dbu 0
set macro_area_dbu 0
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    set type [$master getType]
    set width [$master getWidth]
    set height [$master getHeight]
    set area [expr { wide($width) * wide($height) }]
    if { [string match "CORE*" $type] } {
        set std_cell_area_dbu [expr { $std_cell_area_dbu + $area }]
    } else {
        set macro_area_dbu [expr { $macro_area_dbu + $area }]
    }
}

# === CORE_UTILIZATION =====================================================
#
# Pick a core area such that AFTER repair_design has grown the std-cell
# budget by REPAIR_GROWTH_FACTOR (typical 30-50%), the resulting placement
# density is at most TARGET_POST_REPAIR_DENSITY. Macro area is fixed and
# just consumed from the core budget.
#
#   util = (std + macro) × target_density
#          ─────────────────────────────────
#          (std × growth + macro)
#
# Defaults are calibrated against a representative ASIC flow where a
# static CORE_UTILIZATION of ~20% converged at ~22% post-repair density
# (a working configuration with a substantial std-cell count and small
# macro fraction). With the default REPAIR_GROWTH_FACTOR=1.40 and
# TARGET_POST_REPAIR_DENSITY=0.225, the formula reproduces ~20%
# utilization for that point. Override per-design as needed.
set REPAIR_GROWTH_FACTOR        [env_or_default REPAIR_GROWTH_FACTOR 1.40]
set TARGET_POST_REPAIR_DENSITY  [env_or_default TARGET_POST_REPAIR_DENSITY 0.225]
set CORE_UTILIZATION_FLOOR_PCT  [env_or_default CORE_UTILIZATION_FLOOR_PCT 5.0]
set CORE_UTILIZATION_CEILING_PCT [env_or_default CORE_UTILIZATION_CEILING_PCT 50.0]

set total_initial_area [expr { double($std_cell_area_dbu + $macro_area_dbu) }]
set total_post_repair  [expr { double($std_cell_area_dbu) * $REPAIR_GROWTH_FACTOR + double($macro_area_dbu) }]

if { $total_post_repair <= 0 } {
    set util 20.0
    set util_frac 0.20
    puts "compute_floorplan_shape: WARNING zero post-repair area, falling back CORE_UTILIZATION=$util"
} else {
    set util_frac [expr { $total_initial_area * $TARGET_POST_REPAIR_DENSITY / $total_post_repair }]
    # Clamp to a sane range. The floor is roughly where the placer can still
    # legalize cells; the ceiling is back in the too-tight-for-repair regime.
    set floor [expr { $CORE_UTILIZATION_FLOOR_PCT / 100.0 }]
    set ceil  [expr { $CORE_UTILIZATION_CEILING_PCT / 100.0 }]
    if { $util_frac < $floor } { set util_frac $floor }
    if { $util_frac > $ceil  } { set util_frac $ceil }
    set util [format "%.1f" [expr { $util_frac * 100.0 }]]
}

# === CORE_MARGIN ==========================================================
#
# Distance from the core boundary to the die boundary, in microns. Has to
# fit the PDN ring stack and IO routing tracks. The default 2 µm value
# is a known-safe floor for small/medium designs; it scales mildly with
# die linear dimension so larger designs get more margin headroom for
# ring routing.
#
# Estimated die linear dimension comes from the cells we need to fit and
# the target utilization just picked: die_area_um² ≈ total_initial_um² /
# util_frac; die_linear ≈ sqrt(die_area). The default die-fraction (0.5%)
# is conservative — for a 4 mm² die (die_linear ≈ 2000 µm) it produces
# ≈10 µm; smaller dies stay at the floor.
#
# This is not a deep heuristic — a real one would parse PDN_TCL to extract
# actual ring widths. The shape (max with a floor) is what's important:
# safe for tested designs and grows for designs that get bigger.
set CORE_MARGIN_FLOOR_UM      [env_or_default CORE_MARGIN_FLOOR_UM 2.0]
set CORE_MARGIN_DIE_FRACTION  [env_or_default CORE_MARGIN_DIE_FRACTION 0.005]

# Convert dbu² to µm². Get the actual ratio from the technology rather
# than hardcoding (varies between PDKs).
set dbu_per_micron [[ord::get_db_tech] getDbUnitsPerMicron]
set total_initial_area_um2 [expr { $total_initial_area / (double($dbu_per_micron) ** 2) }]

if { $util_frac > 0.0 } {
    set die_area_um2 [expr { $total_initial_area_um2 / $util_frac }]
} else {
    set die_area_um2 0.0
}
set die_linear_um [expr { sqrt($die_area_um2) }]
set core_margin_raw [expr { $CORE_MARGIN_DIE_FRACTION * $die_linear_um }]
set core_margin [format "%.0f" [expr { $core_margin_raw < $CORE_MARGIN_FLOOR_UM ? $CORE_MARGIN_FLOOR_UM : $core_margin_raw }]]

puts "compute_floorplan_shape: std_cell=$std_cell_area_dbu dbu², macro=$macro_area_dbu dbu²"
puts "compute_floorplan_shape: CORE_UTILIZATION=$util (target post-repair density $TARGET_POST_REPAIR_DENSITY, growth $REPAIR_GROWTH_FACTOR)"
puts "compute_floorplan_shape: CORE_MARGIN=$core_margin µm (die_linear ≈ [format %.0f $die_linear_um] µm, fraction $CORE_MARGIN_DIE_FRACTION, floor $CORE_MARGIN_FLOOR_UM)"

set f [open $::env(OUTPUT) w]
puts $f "{\"CORE_UTILIZATION\": \"$util\", \"CORE_MARGIN\": \"$core_margin\"}"
close $f
