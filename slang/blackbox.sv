// Regression coverage for the slang frontend's blackboxed-module path — the
// class of design that broke in the sv-elab slang-11 migration (OpenROAD
// mock-array, The-OpenROAD-Project/OpenROAD#10884). `leaf` is declared with an
// empty body and blackboxed by name via SYNTH_BLACKBOXES + --empty-blackboxes,
// so a future sv-elab bump that regresses blackbox handling fails here in CI
// instead of surfacing in a downstream.
module leaf (
    input  logic       clock,
    input  logic [7:0] a,
    output logic [7:0] q
);
endmodule

module blackbox_top (
    input  logic       clock,
    input  logic [7:0] a,
    output logic [7:0] q
);
  leaf u_leaf (
      .clock(clock),
      .a(a),
      .q(q)
  );
endmodule
