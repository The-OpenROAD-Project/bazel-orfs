> **Repo**: Applies to every ORFS design configured from this workspace, and to any downstream project that consumes bazel-orfs.

Prefer the slang frontend for synthesis. Set `SYNTH_HDL_FRONTEND = slang` in a design's `config.mk` (or `"SYNTH_HDL_FRONTEND": "slang"` in its arguments) unless the design's Verilog cannot go through slang, and say why in a comment when it cannot.

ARGUMENTS: $ARGUMENTS

## Why

yosys's own Verilog frontend (`read_verilog -sv`) is effectively deprecated for SystemVerilog: it is not a SystemVerilog compiler and its AST elaboration has costs that do not appear in the netlist. Measured on `flow/designs/asap7/wirebound`, four nested generate loops (about half a million scopes) spent minutes in `AstNode::expand_genblock` and `prefix_id`, 55 % of the samples in string growth and memmove, re-prefixing every identifier once per nesting level; the synthesised netlist takes seconds. slang elaborates the same file without that pass, and rejects genuinely broken SystemVerilog instead of guessing.

## How

- New design: `export SYNTH_HDL_FRONTEND = slang`. `SYNTH_SLANG_ARGS` takes extra frontend arguments.
- Existing design on the yosys frontend: switch it, rebuild synthesis, and compare cell and flop counts before trusting anything downstream. A difference is a real elaboration difference, usually one the yosys frontend was silently permissive about.
- When slang refuses a file the yosys frontend accepted (firtool output with constructs slang rejects, or vendor Verilog-2005 with non-standard extensions), keep the yosys frontend and record the reason next to the setting, as `test/coremark_joule/designs/asap7/xiangshan/config.mk` does.
- A canonicalisation step that takes minutes on a small netlist is this until proven otherwise; check the frontend before profiling anything else.

## What this does not decide

Partition and keep-hierarchy choices, ABC settings and the memory extraction are unchanged by the frontend. `SYNTH_HDL_FRONTEND` is synth-scoped, so switching it re-runs synthesis and nothing before it.
