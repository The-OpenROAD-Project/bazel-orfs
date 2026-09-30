# openroad -exit characterise_array.tcl: a structured_gen array's liberty
# from its own placed gates, in place of the generator's formula.
# Environment: XS_LIBS and XS_SETRC as load.tcl, RF_ODB the generator's
# --odb, RF_CELL the module name, RF_LIB the liberty to write.
foreach f [glob $::env(XS_LIBS)/asap7sc7p5t_*.lib] { read_liberty $f }
read_db $::env(RF_ODB)
source $::env(XS_SETRC)
create_clock -name clk -period 473 [get_ports clock]
set_input_transition 10 [all_inputs]
estimate_parasitics -placement
write_timing_model -cell_name $::env(RF_CELL) $::env(RF_LIB)
