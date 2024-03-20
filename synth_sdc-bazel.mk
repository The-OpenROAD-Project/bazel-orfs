.PHONY: bazel-synth_sdc
bazel-synth_sdc:
	mkdir -p $(RESULTS_DIR)
	$(UNSET_AND_MAKE) $(RESULTS_DIR)/1_synth.sdc
