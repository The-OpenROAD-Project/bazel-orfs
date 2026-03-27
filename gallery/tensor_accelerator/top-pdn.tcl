# PDN for tensor_accelerator_top (level 3 — 4x TPC macros + GCP + NoC).
#
# Metal budget: M1-M9, full stack.
# Lower stack (M1/M2/M5/M6) follows BLOCKS_grid_strategy pattern for
# standard cell power. Upper stack (M8/M9) provides macro power delivery.
# TPC macros expose power on M8 → connect M8↔M9.

source $::env(SCRIPTS_DIR)/util.tcl

add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD$} -power
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS$} -ground

set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

# Core grid: full metal stack
define_pdn_grid -name {top} -voltage_domains {CORE} -pins {M9}
add_pdn_stripe -grid {top} -layer {M1} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M2} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_ring -grid {top} -layers {M8 M9} -widths {0.544 0.544} -spacings {0.096} \
  -core_offset {0.544}
# Dense M5 straps bridge M2 followpin gaps between macros
add_pdn_stripe -grid {top} -layer {M5} -width {0.12} -spacing {0.072} -pitch {2.16} \
  -offset {1.50} -extend_to_core_ring
# Upper metal for macro power delivery (skip M6/M7 — blocked by TPC macros)
add_pdn_stripe -grid {top} -layer {M8} -width {0.288} -spacing {0.096} -pitch {4.32} \
  -offset {1.50} -extend_to_core_ring
add_pdn_stripe -grid {top} -layer {M9} -width {0.288} -spacing {0.096} -pitch {8.64} \
  -offset {1.504} -extend_to_core_ring

add_pdn_connect -grid {top} -layers {M1 M2}
add_pdn_connect -grid {top} -layers {M2 M5}
add_pdn_connect -grid {top} -layers {M5 M8}
add_pdn_connect -grid {top} -layers {M8 M9}

# Macro grid: connect TPC M8 pins to core M8/M9 straps
set macro_names {}
foreach macro [find_macros] {
  dict set macro_names [[$macro getMaster] getName] 1
}
if {[dict size $macro_names] > 0} {
  set halo_x $::env(MACRO_ROWS_HALO_X)
  set halo_y $::env(MACRO_ROWS_HALO_Y)
  define_pdn_grid -macro -cells [dict keys $macro_names] \
    -halo "$halo_x $halo_y $halo_x $halo_y" \
    -voltage_domains {CORE} -name MacroGrid
  add_pdn_connect -grid {MacroGrid} -layers {M8 M9}
}
