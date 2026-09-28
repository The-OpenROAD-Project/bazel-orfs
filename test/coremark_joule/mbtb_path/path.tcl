# The analogue's path: start bit 13 of t1_startPcVec_0 to the worst
# setIdx_r[6] of a write-buffer enqueue. The endpoint pattern matches the
# register flat (entryWriteBuffer_io_write_*_setIdx_r), synthesised inside
# the seam module (yosys names it after the port it drives,
# entryWriteBufferEnq.io_write_*_bits_setIdx) and dissolved from its
# generated ODB (entryWriteBufferEnq.io_write_*_bits_setIdx_r).
proc mbtb_path {out} {
  set s [get_cells {t1_startPcVec_0_addr*13*}]
  set e [get_cells -hier {*internalBanks_*io_write_*_bits_setIdx*6*}]
  report_checks -from $s -to $e -path_delay max -fields {slew cap fanout input_pins} -digits 1 > $out
}
