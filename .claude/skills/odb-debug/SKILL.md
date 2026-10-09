---
name: odb-debug
description: >-
  Ask a placed or routed design questions through a persistent OpenROAD session on a
  flow stage's ODB (the odb-debug daemon and its MCP tools): where the macros are, which
  cells sit inside a macro footprint or in a sliver between macros, what check_placement
  and the worst paths say, and whether a period is set by a few outliers or a mass of
  paths (the endpoint histogram and the false-path peel). Use when a legaliser fails or
  stalls, when a floorplan looks wrong, before choosing a fix for a period, or whenever
  the answer is in the database rather than the log.
---

# odb-debug

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/odb-debug.md](../../../.claude/commands/odb-debug.md)
