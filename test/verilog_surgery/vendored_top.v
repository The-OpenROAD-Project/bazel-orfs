// Vendored RTL, kept as upstream has it: synthesis reads the copy that
// surgery.py edits, never this file.
module vendored_top (
    input  a,
    output y
);
  assign y = a;
endmodule
