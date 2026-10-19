# Refused: SDC_FILE names a file that is not there.
export PLATFORM      = asap7
export DESIGN_NAME   = gcd
export VERILOG_FILES = $(DESIGN_HOME)/src/gcd/gcd.v
export SDC_FILE      = $(DESIGN_HOME)/asap7/gcd/no_such_constraint.sdc
