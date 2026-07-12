# Claude Code Instructions

## Git

Always use `git commit -s` to include a `Signed-off-by` trailer.

You may push feature branches and open, comment on, and update pull
requests yourself — on this repo and on external repos (via forks) — but
**only after running the Confidentiality purge** (see below) over
everything that will leave this machine.

**Always human-only, on every repo** — never do these yourself:

- `gh pr merge` (or merging via `gh api`) — merging is the human's call.
- `git push` to `main` or any protected branch. Push to a feature branch
  and open a PR instead.

If you are on `main` or a detached `HEAD`, create a feature branch before
committing.

## Confidentiality purge

Before anything leaves this machine — every PR, PR comment, pushed commit,
issue, or `gh api` write — review the full outbound content and remove or
neutralize:

1. **Local paths & usernames** — absolute local paths (`/home/…`, scratch
   dirs), host/machine names, OS user names. Rewrite to neutral or
   repo-relative form.
2. **Employer & private contacts** — employer or org-internal names,
   private email addresses, and details visible only inside the
   maintainers' organization.
3. **Private URLs & internal references** — private repo/registry URLs,
   internal ticket/issue/PR cross-references, internal branch names, and
   CI/dashboard links.
4. **Secrets & embargoed material** — any token, key, or credential
   (always), and any unpublished or embargoed technical detail that isn't
   already public.

When in doubt, leave it out. If you can't confidently purge something,
stop and ask the human rather than publishing it.

## Formatting

Before committing, run `bazelisk run //:fix_lint` to format and lint all changed files. This is the single source of truth — do NOT run `buildifier` or `black` individually, as `fix_lint` handles all of them with the correct CI-compatible configuration:

- `buildifier` on changed `.bzl`/`BUILD`/`MODULE.bazel` files (respects `.bazelignore`)
- `black` on changed `.py` files

Just run:

```sh
bazelisk run //:fix_lint
```

## Debugging OpenROAD/ORFS failures

When an ORFS stage fails in openroad/yosys/opensta — a crash, a hang, a
parallel race, or a nondeterministic result — the `.claude/commands/`
slash-commands are the single source of truth. Downstream projects that
consume bazel-orfs should point at these rather than duplicating the
mechanics:

- `/openroad-debug` — diagnose the failure (decode the exit code,
  characterize a hang vs race with the `-threads 1` test, set up a fast
  `_deps` + bring-your-own-binary edit/measure loop, split a stage at an ODB
  checkpoint) and shape a self-contained reproducer.
- `/openroad-issue` — file it upstream as a `git am` patch + failing bazel test.
- `/untar-and-run-report` — ship it as an untar-and-run `.tar.gz` archive.
- `/odb-to-cpp` — turn a whittled `.odb` into a self-contained C++ unit test.

## Gallery

`gallery/` is a separate Bazel workspace with its own `MODULE.bazel`.
It contains example ORFS designs that exercise bazel-orfs features.

- **bazelisk** commands for gallery targets require `cd gallery` first
- gallery uses `local_path_override(path = "..")` to reference bazel-orfs,
  so changes to bazel-orfs rules are immediately visible in gallery builds
- Gallery-specific skills are prefixed with `demo-` (e.g., `/demo-add`,
  `/demo-debug`, `/demo-update`)
- Gallery has its own `.bazelrc` and `user.bazelrc` (gitignored)

### External actions

The Git policy above (push / PR / merge rules) and the Confidentiality
purge apply to gallery and external repos too. In short: after a
confidentiality purge you may push feature branches and open, comment on,
and update PRs on any repo. `gh pr merge` and pushes to `main`/protected
branches stay human-only everywhere. Use other GitHub API writes (`gh api`
POST/PUT/PATCH/DELETE) only for an action that is already allowed,
post-purge — never for merges, branch protection, or repo administration.

Prepare the content, run the purge, then publish.
