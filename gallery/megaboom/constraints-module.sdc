set sdc_version 2.0

#
# SDC for per-module netlist synthesis.
# Sub-modules may not have clock/reset ports — synthesis only needs
# a virtual clock for ABC timing optimization.
#

set clk_period 1200
set clk_name  clock

# Try to find a clock port; fall back to a virtual clock.
set clk_port [get_ports -quiet clock]
if {$clk_port == ""} {
    set clk_port [get_ports -quiet clk]
}

if {$clk_port == ""} {
    # Virtual clock — no physical port, just drives ABC timing
    create_clock -period $clk_period -name $clk_name
} else {
    set clk_port_name [get_name $clk_port]

    # Ignore reset if present
    set reset_port [get_ports -quiet reset]
    if {$reset_port != ""} {
        set_false_path -from $reset_port
    }

    source $::env(PLATFORM_DIR)/constraints.sdc
}
