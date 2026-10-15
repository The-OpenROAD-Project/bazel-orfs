---
name: scale-to-memory
description: >-
  Build a design's macros and parent scaled to this machine's memory with orfs_schedule()
  (bazelisk run //<pkg>:build), the bazel-orfs scheduler at home: write the first
  resources.json from a qualitative reading of the design and a fast (minutes) per-instance
  estimate, show the waves with --plan-only, run under a memory scope with swap as a
  backstop, and commit the measured refreshes. Use when a design has more than one hardened
  macro, when a build would run several large flows at once, when resources.json is missing
  or a run says it was updated, or before any multi-hour build on a shared workstation.
---

# scale-to-memory

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/scale-to-memory.md](../../../.claude/commands/scale-to-memory.md)
