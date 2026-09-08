# Routing demand per metal layer, from the global-route guides.
#
# The study's first assertion is that this design is actually in the
# regime it claims: routing reaches the top of the stack, and the top of
# the stack is scarce rather than idle. Both halves are measurements, not
# config settings -- setting MAX_ROUTING_LAYER=M9 permits M8/M9, it does
# not mean a single net went there. A design that quietly routes on M2-M3
# would produce a complete, plausible and worthless study, so this probe
# runs before anything else and the numbers it prints gate the rest.
#
# What is measured: guides, not routed wires. After global route each net
# carries per-GCell guide rectangles naming the layer routing is allowed
# to use, which is the demand global route actually assigned -- and it is
# the only layer-resolved quantity that exists at grt, where the study
# lives. It is reported as guide length, never as wirelength, because a
# guide is a corridor and a wire is not.
#
# Scarcity comes out of the same file: track supply per layer follows the
# layer pitch from the tech LEF, so demand and supply are both here and
# the ratio is the interesting column. asap7's upper layers are coarse --
# M8/M9 pitch 0.08um against M2's 0.045um -- so a congested design can
# want the top of the stack and still not be able to have much of it.
#
# Supply is reported twice, and the second number is the one to read.
# Raw track count is not what global routing may spend:
# ROUTING_LAYER_ADJUSTMENT derates every layer in the routable range to
# leave room for pins, power and vias, so a design at 48% of raw tracks
# is at 64% of what the router will actually hand out. Reporting only the
# raw figure understates contention by exactly that factor.
#
# Layers outside [MIN_ROUTING_LAYER, MAX_ROUTING_LAYER] are marked rather
# than dropped. M1 carries pin-level guides and `Pad` carries none, and
# neither is a layer a signal net may be assigned -- but silently
# omitting them would also hide the case where routing appears on a layer
# the configuration says it cannot use.

source $::env(SCRIPTS_DIR)/load.tcl
set odb_tail [file tail $::env(ODB_FILE)]
set sdc_tail [file rootname $odb_tail].sdc
load_design $odb_tail $sdc_tail

set block [ord::get_db_block]
set tech [[ord::get_db] getTech]
# The block's DBU, matching extract_lib.tcl: one convention for the whole
# study, so two probes can never disagree by a factor of a thousand.
set dbu [$block getDbUnitsPerMicron]

# Routing layers only, bottom to top, with their pitch and direction.
set layer_order {}
array set pitch {}
array set direction {}
array set level {}
foreach layer [$tech getLayers] {
    if { [$layer getRoutingLevel] == 0 } { continue }
    set name [$layer getName]
    lappend layer_order $name
    set pitch($name) [expr { [$layer getPitch] * 1.0 / $dbu }]
    set direction($name) [$layer getDirection]
    set level($name) [$layer getRoutingLevel]
}

array set guide_len {}
array set guide_count {}
foreach name $layer_order {
    set guide_len($name) 0.0
    set guide_count($name) 0
}

set nets_with_guides 0
foreach net [$block getNets] {
    set guides [$net getGuides]
    if { [llength $guides] > 0 } { incr nets_with_guides }
    foreach guide $guides {
        set name [[$guide getLayer] getName]
        if { ![info exists guide_len($name)] } { continue }
        set box [$guide getBox]
        set w [expr { ([$box xMax] - [$box xMin]) * 1.0 / $dbu }]
        set h [expr { ([$box yMax] - [$box yMin]) * 1.0 / $dbu }]
        # A guide's corridor runs along its longer side.
        set guide_len($name) [expr { $guide_len($name) + ($w > $h ? $w : $h) }]
        incr guide_count($name)
    }
}

# A zero here is the failure this probe exists to catch: no guides means
# global route did not run on this ODB, and every per-layer number below
# would be a well-formed zero rather than a finding.
if { $nets_with_guides == 0 } {
    error "no net carries global-route guides in $odb_tail:\
 this ODB is not a post-global-route database, so layer demand is unmeasured"
}

# Track supply: the core's extent across the layer's routing direction,
# divided by the pitch, times the extent along it. Same unit as demand
# (microns of corridor), so the ratio is dimensionless.
set core [$block getCoreArea]
set core_w [expr { ([$core xMax] - [$core xMin]) * 1.0 / $dbu }]
set core_h [expr { ([$core yMax] - [$core yMin]) * 1.0 / $dbu }]

# The routable window and the derate the router applies inside it.
set min_layer [expr { [info exists ::env(MIN_ROUTING_LAYER)] ? $::env(MIN_ROUTING_LAYER) : "" }]
set max_layer [expr { [info exists ::env(MAX_ROUTING_LAYER)] ? $::env(MAX_ROUTING_LAYER) : "" }]
set adjustment [expr { [info exists ::env(ROUTING_LAYER_ADJUSTMENT)] \
    && $::env(ROUTING_LAYER_ADJUSTMENT) ne "" \
    ? $::env(ROUTING_LAYER_ADJUSTMENT) : 0.0 }]
set min_idx [lsearch -exact $layer_order $min_layer]
set max_idx [lsearch -exact $layer_order $max_layer]
if { $min_idx < 0 } { set min_idx 0 }
if { $max_idx < 0 } { set max_idx [expr { [llength $layer_order] - 1 }] }

set total_len 0.0
foreach name $layer_order {
    set total_len [expr { $total_len + $guide_len($name) }]
}

puts "LAYER_USAGE core ${core_w}x${core_h} um, nets with guides: $nets_with_guides,\
 routable ${min_layer}-${max_layer}, adjustment $adjustment"
set rows {}
set idx -1
foreach name $layer_order {
    incr idx
    set routable [expr { $idx >= $min_idx && $idx <= $max_idx }]
    if { $direction($name) eq "HORIZONTAL" } {
        set tracks [expr { $core_h / $pitch($name) }]
        set supply [expr { $tracks * $core_w }]
    } else {
        set tracks [expr { $core_w / $pitch($name) }]
        set supply [expr { $tracks * $core_h }]
    }
    # The derate applies only inside the routable range, which is where
    # fastroute.tcl calls set_global_routing_layer_adjustment.
    set effective [expr { $routable ? $supply * (1.0 - $adjustment) : $supply }]
    set share [expr { $total_len > 0 ? 100.0 * $guide_len($name) / $total_len : 0.0 }]
    set util [expr { $supply > 0 ? 100.0 * $guide_len($name) / $supply : 0.0 }]
    set eff_util [expr { $effective > 0 ? 100.0 * $guide_len($name) / $effective : 0.0 }]
    # Mean guide length is the tell for what a layer is carrying: short
    # guides are local detail, long ones are the die-crossing nets whose
    # resistance the pre-route estimate is mispricing.
    set mean_len [expr { $guide_count($name) > 0 ? $guide_len($name) / $guide_count($name) : 0.0 }]
    puts [format "LAYER_USAGE %-4s level=%d dir=%-10s routable=%d guides=%8d\
 demand=%12.1f um share=%5.2f%% mean=%6.2f um used=%6.2f%% (raw %6.2f%%)" \
        $name $level($name) $direction($name) $routable $guide_count($name) \
        $guide_len($name) $share $mean_len $eff_util $util]
    lappend rows [format {{"layer": "%s", "level": %d, "direction": "%s", "routable": %s, "pitch_um": %g, "guides": %d, "demand_um": %.3f, "share_percent": %.4f, "mean_guide_um": %.4f, "supply_um": %.3f, "effective_supply_um": %.3f, "utilization_percent": %.4f, "effective_utilization_percent": %.4f}} \
        $name $level($name) $direction($name) [expr { $routable ? "true" : "false" }] \
        $pitch($name) $guide_count($name) $guide_len($name) $share $mean_len \
        $supply $effective $util $eff_util]
}

set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"core_width_um\": $core_w,"
puts $fp "  \"core_height_um\": $core_h,"
puts $fp "  \"nets_with_guides\": $nets_with_guides,"
puts $fp "  \"min_routing_layer\": \"$min_layer\","
puts $fp "  \"max_routing_layer\": \"$max_layer\","
puts $fp "  \"routing_layer_adjustment\": $adjustment,"
puts $fp "  \"total_demand_um\": $total_len,"
puts $fp "  \"layers\": \["
puts $fp "    [join $rows ",\n    "]"
puts $fp "  \]"
puts $fp "}"
close $fp
exit 0
