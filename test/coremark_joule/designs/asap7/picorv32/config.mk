export PLATFORM                = asap7

# cmj_picorv32, not picorv32: the parameters this study measures are
# fixed in that module, so the hardened core cannot differ from the
# simulated one. See //test/coremark_joule/rtl/cmj_picorv32.v.
export DESIGN_NAME             = cmj_picorv32
export DESIGN_NICKNAME         = picorv32

export VERILOG_FILES           = @picorv32//:rtl //test/coremark_joule/rtl:cmj_picorv32.v \
                                 //test/coremark_joule/rtl:cmj_progmem.sv //test/coremark_joule/flow:cmj_sram_blackbox.v \
                                 //test/coremark_joule/rtl:cmj_dmem.v
export SDC_FILE                = $(DESIGN_HOME)/asap7/picorv32/constraints.sdc

# Hierarchical synthesis with an explicit kept list, so report_power can
# attribute power to functional units. synth.tcl errors on a name that is
# not in the elaborated design, so this list cannot rot silently.
#
# picorv32's list is short because the core is short: picorv32.v defines
# eight modules and the CPU is one of them. Decode, execute, the ALU and
# control are all inline in that single module, so they cannot be
# attributed. See units.json, which records the waiver rather than
# leaving the gap to be noticed.
export SYNTH_HIERARCHICAL      = 1
# Not picorv32_regs: upstream instantiates it only when the PICORV32_REGS
# macro is defined, and that define is commented out, so the register
# file is an inline array inside the picorv32 module. The macro exists
# precisely to break it out, but using it would change the design from
# the one its author ships -- so the default stands and the register file
# falls into "other" along with the datapath.
export SYNTH_KEEP_MODULES      = picorv32_pcpi_mul picorv32_pcpi_div

# On, and it correctly converts nothing here. picorv32's register file is
# an inline `reg [31:0] cpuregs [0:31]` array rather than a module, and
# patches/0066 makes the flow leave such a memory alone with a reason:
# an inline array is the design asking for flip-flops. memories.json
# records cpuregs as idiomatic:false and blackboxes.txt is empty, so the
# inventory and the netlist agree.
#
# To harden this register file as a macro the design has to instantiate
# it as a module -- picorv32 offers the PICORV32_REGS mechanism for
# exactly that.
# Run OpenROAD hierarchically, so the module boundaries SYNTH_KEEP_MODULES
# preserved survive into the ODB and the written netlist.
#
# Without it the flow is flat: the ODB carries no module structure and
# write_verilog emits one flattened module, so there is nothing for
# `report_power -saif -instances` to attribute power to. Keeping the
# hierarchy through synthesis and then discarding it in OpenROAD would
# leave the whole functional-unit breakdown with a single unit in it.
export OPENROAD_HIERARCHICAL    = 1

# The memories the tile hardens: the scaler's views of the SRAMs in
# rtl/cmj_sram_models.sv (flow/BUILD.bazel generates them). One model
# for every memory on every point is the reason for the choice -- the
# memory is over half of each point's power, and a cross-core energy
# comparison cannot afford to have its largest term come from two
# different models -- and, unlike the FakeRAM2.0 views the study used
# first, this model's energy and leakage depend on the memory's shape
# (§5.1, §8.5). The flow sees each SRAM's boundary in
# flow/cmj_sram_blackbox.v and nothing else; AUTO_MEMORIES stays off
# because there is nothing left for it to find or convert.
export ADDITIONAL_LEFS         = //test/coremark_joule/flow:cmj_imem_sram.lef \
                                 //test/coremark_joule/flow:cmj_dmem_lane_sram.lef
export ADDITIONAL_LIBS         = //test/coremark_joule/flow:cmj_imem_sram.lib \
                                 //test/coremark_joule/flow:cmj_dmem_lane_sram.lib

# Two macros in a design whose standard-cell half is small. Taken from
# the veer config, which is the design in this study that already had
# macros in it.
export PLACE_DENSITY_LB_ADDON  = 0.20
export MACRO_PLACE_HALO        = 2 2

# Starting points. The auto_floorplan derivation measures and pins these.
# 50, not the 40 the cacheless cores used before section 5.1. The
# memories are most of the design area now, so utilization decides
# almost nothing about the standard cells and everything about how much
# empty die the clock tree has to cross.
#
# Macro placement is RTL-MP's. An earlier revision placed the two macros
# by hand because RTL-MP could not partition two of them against a
# standard-cell half this small (MPL-0045); with the data memory split
# into four byte lanes there are five, and the placer converges on its
# own. What that gives up is a placement identical across the three
# cores, so the memory's wirelength -- and the switching power in it --
# is no longer a controlled constant between them.
export CORE_UTILIZATION        = 50
export PLACE_DENSITY           = 0.65

# Metrics reporting off. This is the only line of the FAST_SETTINGS dict
# in //test:BUILD that a measurement study can take -- every other entry
# in it changes the netlist, and a study cannot buy speed with the thing
# it measures. §3.6 of the paper has the list and the reasoning.
#
# Nothing here reads ORFS's metrics: power comes from
# flow/power_grt.tcl, the achieved period from flow/period_probe.tcl,
# and auto_floorplan takes WNS from sta::worst_slack_cmd directly.
export SKIP_REPORT_METRICS     = 1
