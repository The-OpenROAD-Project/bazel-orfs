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

# Map inferred memories onto generated SRAM views rather than hardening
# them as flops.
export AUTO_MEMORIES           = 1

# Starting points. The auto_floorplan derivation measures and pins these.
export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
