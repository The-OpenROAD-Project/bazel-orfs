# Claude-Augmented Git Flow

A workflow philosophy where Feature Requests (FRs) are the primary artifact
and Claude bridges the gap between ideas and mergeable code.

## TL;DR: Got a Half-Cooked PR? Write a Feature Request

Don't let a stalled PR rot. Convert it to a FR with the patch attached as
"this is what I tried and this is what I saw." Include the data — logs,
measurements, error messages, timing results — directly in the FR.

This can be **enormously time-saving**. The data gathered during a failed
attempt (reproduction steps, performance numbers, edge cases discovered) can
represent minutes, hours, days, or even weeks of work. A PR that doesn't
merge still carries irreplaceable empirical evidence. The FR preserves that
evidence as a first-class artifact. See
[Immutable ODB with Command Journal](immutable-odb-command-journal.md) for
an example: the prior art survey alone took significant research effort that
would be lost if the PR were simply closed.

## The Key Insight: Value Lives in Ideas, Not Code

- **Doing is cheap.** Claude can generate PRs freely. Code itself has no
  intrinsic value.
- **Ideas are valuable.** A well-scoped FR that solves a real need is where
  value is protected.
- **Projects fail on direction, not execution.** Getting the *what* right
  matters more than the *how*.

## Core Conversions

| From | To | Safety |
|------|-----|--------|
| PR → FR | Always safe | Human + Claude extract intent from code; FR includes what was attempted and why it wasn't merged |
| FR → PR | Always safe | Human guides Claude to implement the idea |
| PR → FR → PR | Always safe | The full review/rewrite cycle |
| Merging foreign PR | **Risky** | Unknown intent, unknown quality |
| Merging foreign PR → FR → PR | Safe | Intent extracted, code rewritten |

Every conversion has a **human in the loop** — Claude assists with extraction
and implementation, but humans decide what to extract, what matters, and what
to build.

## The Flow

```
Contributor idea
      |
  PR (bad code, good idea)
      |
  Human + Claude extract intent
      |
  FR (intent + what was tried + why it didn't merge yet)
      |  stored in git with authorship
      |
  Human reviews FR (was this the right thing to build?)
      |
      | Human guides Claude
      |
  PR (clean implementation)
      |
  Human reviews + merges
```

## Why This Works

### Reviewing shifts from hard to easy

- **Reviewing a PR is hard.** Is the code correct? Safe? Idiomatic? Complete?
- **Reviewing a FR is easy.** Does this solve a real problem? Is the scope
  right? Is this wanted?

Shift review burden to the FR stage, where humans are best equipped to judge.

### Authorship is preserved

When a contributor submits a bad PR with a good idea:

1. Maintainer extracts intent → FR (stored in git, preserves author + lineage)
2. Claude implements → new PR
3. **Original contributor remains the author of the idea**

The FR is the artifact of record. Git history shows who had the insight.

### Lower friction, not just safer

FR discussions are async, low-stakes, text-based conversations — the kind
humans are comfortable with. PRs carry the weight of "this might break
something, someone has to fix it, and the clock is ticking."

Claude doesn't just fill an execution gap. It absorbs the part of software
development that burns people out.

## Principles

- Gate on **ideas**, not **code quality**
- Claude handles the execution gap between a good idea and a mergeable PR
- FRs are first-class citizens in git — not throwaway issue tracker text
- A contributor who can't code can still be a valued author
