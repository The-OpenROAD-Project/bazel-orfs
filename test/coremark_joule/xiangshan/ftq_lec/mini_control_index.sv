// Ftq's BPU-train read in miniature, 8 entries of 4 bits: the read data
// is captured only in the else branch of if (_GEN_7), as in the
// elaborated Ftq, where every use of _metaQueueResolve_io_readPorts_0_data
// is. Here: negative control: the previous train's index.
module FtqMini(
  input        clock,
  input        reset,
  input        flushTrainCache,
  input        bpuTrain_ready,
  input        bpuTrain_valid,
  input  [2:0] bpuTrain_ftqIdx,
  input  [2:0] trainIndexCache_value,
  input        meta_wen,
  input  [2:0] meta_waddr,
  input  [3:0] meta_wdata,
  output [3:0] train_meta,
  output       train_valid
);
  wire [3:0] _rf_io_readPorts_0_data;
  wire       _GEN_6 = bpuTrain_ready & bpuTrain_valid;
  wire       _GEN_7 = flushTrainCache | ~_GEN_6;
  reg  [3:0] trainCache_bits_meta;
  reg        trainCache_valid;
  RfMini metaQueueResolve (
    .clock                (clock),
    .io_readPorts_0_addr  (trainIndexCache_value),
    .io_readPorts_0_data  (_rf_io_readPorts_0_data),
    .io_writePorts_0_wen  (meta_wen),
    .io_writePorts_0_addr (meta_waddr),
    .io_writePorts_0_data (meta_wdata)
  );
  always @(posedge clock or posedge reset) begin
    if (reset) begin
      trainCache_valid <= 1'h0;
      trainCache_bits_meta <= 4'h0;
    end
    else begin
      trainCache_valid <= ~flushTrainCache & (_GEN_6 | trainCache_valid);
      if (_GEN_7) begin
      end
      else begin
        trainCache_bits_meta <= _rf_io_readPorts_0_data;
      end
    end
  end
  assign train_meta = trainCache_bits_meta;
  assign train_valid = trainCache_valid & ~flushTrainCache;
endmodule
