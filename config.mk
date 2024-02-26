# Hmmm.... PLATFORM can't be passed on the command line as "make PLATFORM=asap7", because
# include of the platform config.mk doesn't see PLATFORM=aspa7.
export PLATFORM=asap7

export WORK_HOME_READ?=$(WORK_HOME)

# $(MAKE_PATTERN) stores the path to file with make patterns
# that will be called in the given flow.
include $(MAKE_PATTERN)
