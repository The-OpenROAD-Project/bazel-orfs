# Wrapper Makefile for parallel synthesis targets.
# Includes the ORFS Makefile and adds targets that are not yet in the
# upstream docker image.

include $(FLOW_HOME)/Makefile

.PHONY: do-yosys-keep
do-yosys-keep: yosys-dependencies
	$(SCRIPTS_DIR)/synth.sh $(SYNTH_KEEP_SCRIPT) $(LOG_DIR)/1_1_yosys_keep.log

.PHONY: do-yosys-partition
do-yosys-partition: yosys-dependencies
	bash $(SYNTH_PARTITION_SCRIPT)

.PHONY: do-yosys-sdc-copy
do-yosys-sdc-copy:
	mkdir -p $(dir $(RESULTS_DIR)/1_2_yosys.sdc)
	cp $(SDC_FILE) $(RESULTS_DIR)/1_2_yosys.sdc
