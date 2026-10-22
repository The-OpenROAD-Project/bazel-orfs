---
name: idea
description: >-
  Write an idea down in bazel-orfs's ideas/ directory: a proposal, a measurement plan or an
  answered question, with a Status line that says where it stands. Checks for an existing entry
  first and updates that instead of adding a duplicate. Use when the human asks to capture an
  idea, or when a study's answer belongs somewhere a later session will find it.
---

> **Repo**: bazel-orfs. Writes `ideas/<slug>.md` and commits it on a feature branch.

Capture an idea in `ideas/`, where the next session, or another machine, can pick it up.

ARGUMENTS: $ARGUMENTS

## Workflow

1. **Check for an existing entry.** Search `ideas/` for the subject (`grep -ril <term> ideas/`) and read what is there. If an entry covers it, update that entry, its Status line included, instead of adding a new one.

2. **Write `ideas/<slug>.md`**, slug lowercase-hyphenated (`flush-pipe.md`). The shape the entries here share:

   ```markdown
   # <Title: the idea, or the answer once there is one>

   Status: **<proposed, not built | run, and answered | partly overtaken by events | ...>** <One or two sentences on where it stands.>

   ## Problem
   <What is wrong or missing, concretely, with a number where there is one.>

   ## Idea
   <What would change.>

   ## Impact
   <Who benefits and how much; measured, or say it is not.>

   ## Effort
   <trivial / small / medium / large, and what the work is.>
   ```

   Images an entry needs go next to it in `ideas/` (`<slug>.png`).

3. **Commit on a feature branch**, never on `main`: `git commit -s -m "ideas: <title>"`. A pull request follows only when the human asks for one.

An idea is written down, not acted on: no code changes, upstream issues or pull requests come from writing one.
