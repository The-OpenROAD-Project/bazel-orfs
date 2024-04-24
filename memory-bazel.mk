.PHONY: memory
memory: $(RESULTS_DIR)/mem.json
	python3 $(MEMORY_DUMP_PY) $(RESULTS_DIR)/mem.json

$(RESULTS_DIR)/mem.json: yosys-dependencies
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	$(TIME_CMD) $(YOSYS_CMD) $(YOSYS_FLAGS) -c $(MEMORY_DUMP_TCL) 2>&1 | tee $(LOG_DIR)/1_0_mem.log
