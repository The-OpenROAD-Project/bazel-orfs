---
name: dogfooding
description: >-
  The standing rules learned building XiangShan with bazel-orfs, for any large design: fix
  the tools and never the design (no multicycle or false-path exceptions, no added RTL
  registers); hard stops where a problem is made; finish the macros before the parent; a
  design README says what is; public PR tests check intended behaviour, not golden .ok
  output; a PR on an unmerged upstream PR is a draft; choices in the flow script, facts in
  the .odb; relative paths; unattended means continue; Chesterton's fence, check
  what our flow skipped before blaming a tool; watch a run that grinds past its expected
  time. Use before proposing a fix for a timing or flow problem found
  on a big design, before writing a design README or status, before opening a PR that
  depends on another, and before writing a test for a public PR.
---

# dogfooding

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/dogfooding.md](../../../.claude/commands/dogfooding.md)
