---
name: cache-miss
description: >-
  Find out why a target is not a remote cache hit on this machine when another machine built
  it, or why it rebuilds when nothing seemed to change: capture a few kilobytes of key
  evidence per machine (Bazel version, commit, redacted options, tool digests, one line per
  action with its cache key and which of arguments, environment, tools, sources or design
  inputs moved), commit it next to the design and diff it. Use when XSTile_grt or any long
  flow target rebuilds unexpectedly, or before blaming Scala, a toolchain or the cache.
---

# cache-miss

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/cache-miss.md](../../../.claude/commands/cache-miss.md)
