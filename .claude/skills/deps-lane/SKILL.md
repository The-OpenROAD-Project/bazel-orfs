---
name: deps-lane
description: >-
  Run a flow's stages by hand in one tree, stage after stage, with `bazelisk run //:deps --
  start <flow> <stage>`, `next <stage>`, `status` and `archive`: minutes per change during
  bring-up instead of rebuilds, at the price of dependencies not being respected and results
  that never reach the Bazel cache. Says when a number from the lane, with its caveat, is
  better than no number (perfection is the enemy of the good: hours-long builds, low risk, a
  clean build coming anyway) and when it is not enough (A/B arms, numbers a decision rests on,
  an uncertain tree history). Use when iterating on a stage's settings or scripts, when
  deploying a stage to debug it, or before quoting a number from a deployed tree.
---

# deps-lane

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/deps-lane.md](../../../.claude/commands/deps-lane.md)
