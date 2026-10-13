---
name: check-setup
description: >-
  Find the registers a design's timing never sees and the setup problems behind them with
  OpenSTA's check_setup: what each of its warnings means (from search/CheckTiming.cc), why
  the bare count in ORFS's 2_1_floorplan.log is not enough, how to get the pins and the
  modules they sit in through odb-debug's check_setup tool, which warnings an SDC written
  with set_max_delay produces by design, and the blind spot carried patch 0109 closes (a
  register the clock reaches only on the edge it does not launch on). Use before quoting a
  period on a new or changed design, when a path you expect is "No paths found", when a
  clock gate or a tie cell sits in a clock path, or when someone says "check_setup is
  clean".
---

# check-setup

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/check-setup.md](../../../.claude/commands/check-setup.md)
