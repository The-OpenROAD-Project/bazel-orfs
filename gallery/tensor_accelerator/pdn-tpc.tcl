# PDN for tensor_processing_cluster (level 2 — 1x systolic_array macro + DMA/VPU/LCP/SRAM).
#
# Metal budget: M1-M8 for routing + PDN, expose pins on M8.
# systolic_array macro exposes power on M6 → connect M6↔M7.

source $::env(SCRIPTS_DIR)/util.tcl

add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD$} -power
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS$} -ground

set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

# Core grid: standard cells (DMA, LCP, VPU, SRAM glue) + straps
define_pdn_grid -name {top} -voltage_domains {CORE} -pins {M8}
add_pdn_stripe -grid {top} -layer {M1} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M2} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_ring -grid {top} -layers {M7 M8} -widths {0.544 0.544} -spacings {0.096} \
  -core_offset {0.544}
add_pdn_stripe -grid {top} -layer {M7} -width {0.288} -spacing {0.096} -pitch {4.32} \
  -offset {1.50} -extend_to_core_ring
add_pdn_stripe -grid {top} -layer {M8} -width {0.288} -spacing {0.096} -pitch {8.64} \
  -offset {1.504} -extend_to_core_ring

add_pdn_connect -grid {top} -layers {M1 M2}
add_pdn_connect -grid {top} -layers {M2 M7}
add_pdn_connect -grid {top} -layers {M7 M8}

# Macro grid: connect systolic_array M6 pins to core M7 straps
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
  add_pdn_connect -grid {MacroGrid} -layers {M6 M7}
}
