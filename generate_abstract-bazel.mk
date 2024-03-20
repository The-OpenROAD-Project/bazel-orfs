.PHONY: bazel-generate_abstract
bazel-generate_abstract:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	$(UNSET_AND_MAKE) do-generate_abstract

.PHONY: bazel-generate_abstract_mock_area
bazel-generate_abstract_mock_area: bazel-generate_abstract
	cp $(WORK_HOME)/results/$(PLATFORM)/$(DESIGN_NICKNAME)/mock_area/$(DESIGN_NAME).lef $(RESULTS_DIR)/

