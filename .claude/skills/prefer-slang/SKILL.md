---
name: prefer-slang
description: >-
  Set SYNTH_HDL_FRONTEND=slang for synthesis unless the design's Verilog cannot go through
  slang; yosys's own Verilog frontend is effectively deprecated for SystemVerilog and its
  generate-block expansion can take minutes on a netlist that synthesises in seconds. Use when
  configuring a design, when canonicalisation is slow, or when choosing between the frontends.
---

# prefer-slang

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/prefer-slang.md](../../../.claude/commands/prefer-slang.md)
