# Peel a block's output flops into a wrapper (yosys -c, structure only).
#
# The flops that drive an output port directly stay in module
# $PEEL_MODULE, now a thin wrapper; everything else moves to
# ${PEEL_MODULE}_core. The parent instantiates $PEEL_MODULE as before,
# flattens the wrapper, and hardens the core, so its placer puts the
# flops anywhere along the crossing. A flop whose Q also feeds logic
# inside gets a core input pin for it (submod adds the port); its own
# hold mux folds into the flop (opt_dff) and moves with it.
#
# PEEL_RTL      the block's Verilog/SystemVerilog, space separated
# PEEL_MODULE   the block to peel
# PEEL_WRAPPER  where to write the wrapper ($PEEL_MODULE)
# PEEL_CORE     where to write the core (${PEEL_MODULE}_core)
# PEEL_PARAMS   optional parameter overrides, "NAME VALUE ..."

set module $::env(PEEL_MODULE)
foreach f $::env(PEEL_RTL) {
  yosys read_verilog -sv $f
}
if { [info exists ::env(PEEL_PARAMS)] } {
  foreach {name value} $::env(PEEL_PARAMS) {
    yosys chparam -set $name $value $module
  }
}
yosys hierarchy -top $module
yosys proc
yosys opt_dff
yosys opt_clean

set flops {t:$dff t:$dffe t:$adff t:$adffe t:$sdff t:$sdffe t:$sdffce}
set unions [string repeat " %u" [expr { [llength $flops] - 1 }]]
yosys "select -set peel_flops o:* %a %ci1 $flops$unions %i"
yosys "select -set peel_core c:* @peel_flops %d"
yosys "submod -name ${module}_core @peel_core"

yosys "select $module"
yosys "write_verilog -noattr -selected $::env(PEEL_WRAPPER)"
yosys "select ${module}_core"
yosys "write_verilog -noattr -selected $::env(PEEL_CORE)"
puts "peel: $module, its output flops into the wrapper, the rest into ${module}_core"
