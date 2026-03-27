# CoralNPU spatial intent — curated by human + Claude
#
# Sourced via PRE_GLOBAL_PLACE_TCL before global_placement.
# Like constraints.sdc captures timing intent, this captures spatial intent.
#
# Sources:
#   - GRT congestion breakdown: 48,307 total overflow
#     M2: 72.6% usage, 8,806 overflow
#     M3: 76.9% usage, 11,733 overflow
#     M4: 61.4% usage, 10,073 overflow
#     M5: 65.8% usage, 6,797 overflow
#     M6: 43.6% usage, 5,797 overflow
#     M7: 33.5% usage, 5,101 overflow
#
# Strategy: uniform congestion across all layers suggests the design is
# globally too dense at 0.65 PLACE_DENSITY. Rather than just lowering the
# global density (already changed to 0.55), we can also create soft
# placement blockages in known-congested regions to spread cells out
# where it matters most.
#
# Phase 1: conservative layer adjustments only (no region-specific tips yet
# until we see the new placement with GPL_ROUTABILITY_DRIVEN=1).

# --- Placeholder for region-specific tips after first run ---
# After the first placement with the new settings, inspect the density
# heatmap and GRT congestion. Then add targeted tips like:
#
#   # Reduce placement density in FPU cluster region
#   create_blockage -region {x1 y1 x2 y2} -max_density 40 -soft
#
#   # Keep register file spread out
#   create_blockage -region {x1 y1 x2 y2} -max_density 35 -soft

puts "placement-tips.tcl: loaded (no region constraints yet — inspect first run)"
