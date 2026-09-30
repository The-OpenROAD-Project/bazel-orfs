# Frontend's synthesis netlist in a standalone OpenROAD session, for
# ideas/xiangshan-frontend-synth.md. Environment:
#   XS_LIBS      directory of uncompressed liberty: the platform's cells
#                (asap7sc7p5t_*.lib) and the FakeRAM arrays (array_*.lib)
#   XS_FTQ_LIBS  directory holding the four Ftq*.lib, formula or
#                characterised (characterise_array.tcl)
#   XS_ODB       the 1_synth.odb to time, as synthesis or fanout_tree wrote it
#   XS_SDC       the flow's 1_synth.sdc
#   XS_SETRC     the platform's setRC.tcl
foreach f [concat [glob $::env(XS_LIBS)/asap7sc7p5t_*.lib] [glob -nocomplain $::env(XS_LIBS)/array_*.lib]] {
  read_liberty $f
}
foreach f [glob $::env(XS_FTQ_LIBS)/Ftq*.lib] { read_liberty $f }
read_db $::env(XS_ODB)
read_sdc $::env(XS_SDC)
source $::env(XS_SETRC)
