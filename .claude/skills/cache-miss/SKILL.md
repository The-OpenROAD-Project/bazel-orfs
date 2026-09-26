---
name: cache-miss
description: >-
  Ask whether a target is a remote cache hit on this machine without building it (a capture
  kills every miss as it appears and lists the actions behind it as not reached, minutes on
  a laptop), and find out why it is not when another machine built it: a few kilobytes of key
  evidence per machine (Bazel version, commit and tree, redacted options, tool digests, the
  source files read, one line per action with its cache key and which of arguments,
  environment, tools, sources or design inputs moved), committed next to the design and
  diffed, naming the first action that differs and the source file behind it. Says what
  committed evidence promises and when to recapture. Use before building any long flow
  target, when XSTile_grt or any stage rebuilds unexpectedly, or before blaming Scala, a
  toolchain or the cache.
---

# cache-miss

The instructions for this skill are maintained in the shared Claude slash command.
Please read and follow the single source of truth:
[../../../.claude/commands/cache-miss.md](../../../.claude/commands/cache-miss.md)
