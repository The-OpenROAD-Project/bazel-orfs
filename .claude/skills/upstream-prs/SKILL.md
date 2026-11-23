---
name: upstream-prs
description: >-
  Check open pull requests across OpenROAD, ORFS and OpenSTA with
  @bazel-orfs//tools/upstream_prs: find actionable PRs (excluding PRs merely
  waiting on a reviewer, treating CI-Public/pr-head red as needing a merge
  commit while leaving CI-Public/pr-merge red alone when pr-head is green),
  rank reviewer-waiting PRs by empirical reviewer-active days, and flag PRs
  waiting 4 or more active days as ping candidates. Use whenever asked what
  can be done upstream, which OpenROAD/ORFS/OpenSTA PRs need attention, or how
  long reviewers have been inactive.
---

> **Repo**: Run from bazel-orfs or any workspace that depends on it. Every write to an upstream repository still needs the human's explicit order (`CLAUDE.md`, "Upstream repositories").

Triage open pull requests across `The-OpenROAD-Project/{OpenROAD, OpenROAD-flow-scripts, OpenSTA}` without hand-assembling GraphQL queries or guessing reviewer schedules.

ARGUMENTS: $ARGUMENTS

## 1. Check what is actionable upstream

When asked which upstream pull requests need attention or what can be done to move things forward, run:

```sh
bazelisk run @bazel-orfs//tools/upstream_prs -- --actionable
```

Add repeatable `--exclude <repo>#<number>` (for example `--exclude ORFS#123`) for any pull request parked on an external call or design thread.

What `--actionable` surfaces, and what it leaves out:

- **PRs merely waiting on a reviewer (`< 4.0` active days) are excluded.** Do not list them when looking for actionable work, and never suggest pinging a reviewer under 4 active days without new technical information to add.
- **`CI-Public/pr-head` red is actionable (author's move).** Reviewers skip pull requests whose `pr-head` is red even when `pr-merge` is green or red. Once the human orders it, push a fast-forward `git commit -s` merge of upstream `master` onto the branch so `pr-head` reruns cleanly.
- **`CI-Public/pr-merge` red with `pr-head` green is NOT actionable.** Leave it alone: pushing a merge commit risks turning a green `pr-head` red on a transient flake. Wait for `pr-merge` to rerun.
- **Other author-move items:** merge conflicts (`CONFLICTING`), failing lint or GitHub Actions checks, unresolved inline review threads whose last comment is not the author's, and human reviews or comments with no subsequent non-merge commit or reply.
- **Ping candidates (`>= 4.0` active days, `--ping-days`):** Reviewer-waiting pull requests that have accumulated 4 or more expected reviewer-active days are listed separately as candidates where a ping may be considered.

## 2. Rank PRs waiting on reviewers

When asked who the next move belongs to or how long open pull requests have been waiting on review, run:

```sh
bazelisk run @bazel-orfs//tools/upstream_prs
```

Pass `--markdown` for a GitHub Markdown table.

How reviewer inactivity is measured:

- **Clock start:** After the latest human reviewer event (or PR creation if none), the clock starts at the author's latest non-merge commit, or first prose reply when no code change was needed. `Merge ...` maintenance commits, bot comments, `/gemini review`, and follow-up pings do not reset the wait time.
- **Empirical active days, not hardcoded calendars:** Over the preceding `--weeks` weeks (default `12`), the tool queries each reviewer's actual review, comment, and merge dates across OpenROAD, ORFS, and OpenSTA to estimate their reaction probability `p[Mon..Sun]` in `[0, 1]`. Regional weekends (such as Friday–Saturday off, Sunday–Thursday active), weekend-active maintainers, and part-time reviewers follow directly from observation. Rows at or above `4.0` expected active days are marked `[PING]`.
