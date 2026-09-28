# The analogue's path: start bit 13 of t1_startPcVec_0 to the worst setIdx_r[6].
proc mbtb_path {out} {
  set s [get_cells {t1_startPcVec_0_addr*13*}]
  set e [get_cells -hier {*internalBanks_*entryWriteBuffer_io_write_*_bits_setIdx_r*6*}]
  report_checks -from $s -to $e -path_delay max -fields {slew cap fanout input_pins} -digits 1 > $out
}
