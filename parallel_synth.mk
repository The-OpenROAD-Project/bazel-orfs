# Wrapper Makefile for parallel synthesis targets.
# Includes the ORFS Makefile and adds targets that are not yet in the
# upstream docker image.

include $(FLOW_HOME)/Makefile

.PHONY: do-yosys-keep
do-yosys-keep: yosys-dependencies
	$(SCRIPTS_DIR)/synth.sh $(SYNTH_KEEP_SCRIPT) $(LOG_DIR)/1_1_yosys_keep.log

# Per-module re-canonicalization, run once per kept module to produce a
# stable per-module RTLIL slice that the partition action keys on.
#
# DESIGN_NAME stays as the surrounding macro's top (ORFS's Makefile uses
# DESIGN_NAME to compute RESULTS_DIR/LOG_DIR). The per-module target is
# passed in MODULE_TARGET_NAME, with characters that would upset the
# filesystem ($, [, ], .) sanitised for the log filename.
#
# Does NOT depend on yosys-dependencies: this step is pure
# read_rtlil → blackbox → write_rtlil, with the input checkpoint already
# materialised by the upstream canonicalize action. Pulling in
# yosys-dependencies would force every macro .lib / verilog file as a
# Make prereq even though yosys never opens them here — defeats the
# point of scoping the per-module action's Bazel inputs.
.PHONY: do-yosys-canonicalize-module
do-yosys-canonicalize-module:
	$(SCRIPTS_DIR)/synth.sh $(SYNTH_CANONICALIZE_MODULE_SCRIPT) $(LOG_DIR)/1_1_yosys_canonicalize_$(shell printf '%s' "$(MODULE_TARGET_NAME)" | tr '$.[]' '____').log

.PHONY: do-yosys-partition
do-yosys-partition: yosys-dependencies
	bash $(SYNTH_PARTITION_SCRIPT)

.PHONY: do-yosys-sdc-copy
do-yosys-sdc-copy:
	mkdir -p $(dir $(RESULTS_DIR)/1_2_yosys.sdc)
	cp $(SDC_FILE) $(RESULTS_DIR)/1_2_yosys.sdc
