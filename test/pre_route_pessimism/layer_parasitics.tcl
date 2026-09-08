# The platform's per-layer RC table, with one thing changed: which layer
# stands in for "an average wire".
#
# This is the study's central knob, and it is a knob rather than a fact.
# Pre-route stages have no routing to measure, so `estimate_parasitics
# -placement` prices every net from the single resistance and
# capacitance `set_wire_rc` installs. asap7 installs an absolute
# constant that corresponds to a lower-middle layer; sky130hd instead
# names a layer and inherits its RC. Neither is calibrated against what
# a particular design's router actually does.
#
# So the gap between what placement thinks the period is and what global
# routing says is not a fixed property of the flow. It is set by this one
# number, and choosing it differently moves the gap in either direction.
# Which matters because every repair budget downstream of placement --
# TNS_END_PERCENT, SETUP_SLACK_MARGIN, and which stages may act at all --
# is tuned against that gap. A budget fitted to one PDK constant is
# fitted to the constant, not to the design.
#
# The per-layer table is taken from the platform unchanged, so an arm
# differs from the stock flow in exactly one line and nothing else can
# account for a difference between arms.
source $::env(PLATFORM_DIR)/setRC.tcl

if { ![info exists ::env(WIREBOUND_WIRE_RC_LAYER)]
     || $::env(WIREBOUND_WIRE_RC_LAYER) eq "" } {
    # No override: the platform's own choice stands, and this file is a
    # no-op wrapper. Reported rather than silent, so a run cannot appear
    # to be an arm of the sweep when it is the control.
    puts "WIRE_RC layer=platform (no override)"
    return
}

set layer $::env(WIREBOUND_WIRE_RC_LAYER)

# Fail if the layer does not exist. A typo'd layer name would otherwise
# leave the platform's constant in place and the arm would report the
# control's numbers under the arm's name -- a clean, plausible, wrong
# result of exactly the kind this study is about.
set tech [[ord::get_db] getTech]
set found ""
foreach tech_layer [$tech getLayers] {
    if { [$tech_layer getRoutingLevel] == 0 } { continue }
    if { [$tech_layer getName] eq $layer } {
        set found $tech_layer
        break
    }
}
if { $found eq "" } {
    error "WIREBOUND_WIRE_RC_LAYER=$layer is not a routing layer in this technology"
}

set_wire_rc -signal -layer $layer
set_wire_rc -clock -layer $layer
puts "WIRE_RC layer=$layer level=[$found getRoutingLevel]"
