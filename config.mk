# Hmmm.... PLATFORM can't be passed on the command line as "make PLATFORM=asap7", because
# include of the platform config.mk doesn't see PLATFORM=aspa7.
export PLATFORM=asap7

export WORK_HOME_READ?=$(WORK_HOME)

-include $(BAZEL_ORFS)/clock_period-bazel.mk
-include $(BAZEL_ORFS)/synth-bazel.mk
-include $(BAZEL_ORFS)/synth_sdc-bazel.mk
-include $(BAZEL_ORFS)/floorplan-bazel.mk
-include $(BAZEL_ORFS)/place-bazel.mk
-include $(BAZEL_ORFS)/cts-bazel.mk
-include $(BAZEL_ORFS)/grt-bazel.mk
-include $(BAZEL_ORFS)/route-bazel.mk
-include $(BAZEL_ORFS)/final-bazel.mk
-include $(BAZEL_ORFS)/generate_abstract-bazel.mk
