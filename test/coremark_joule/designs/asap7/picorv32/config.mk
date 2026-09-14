export PLATFORM                = asap7

# cmj_picorv32, not picorv32: the parameters this study measures are
# fixed in that module, so the hardened core cannot differ from the
# simulated one. See //test/coremark_joule/rtl/cmj_picorv32.v.
export DESIGN_NAME             = cmj_picorv32
export DESIGN_NICKNAME         = picorv32

export VERILOG_FILES           = @picorv32//:rtl //test/coremark_joule/rtl:cmj_picorv32.v
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

export AUTO_MEMORIES           = 1

# Starting points. The auto_floorplan derivation measures and pins these.
export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
