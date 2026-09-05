# Claude Code Instructions

## Git

Always use `git commit -s` to include a `Signed-off-by` trailer.

You may push feature branches and open, comment on, and update pull
requests yourself **on this repo** — but **only after running the
Confidentiality purge** (see below) over everything that will leave this
machine.

**Always human-only, on every repo** — never do these yourself:

- `gh pr merge` (or merging via `gh api`) — merging is the human's call.
- `git push` to `main` or any protected branch. Push to a feature branch
  and open a PR instead.
- **Anything that writes to an upstream repository** — ORFS, OpenROAD,
  yosys, the BCR, any repo that is not bazel-orfs: opening a pull request
  or issue, commenting on one, pushing a branch to a fork for one. See
  "Upstream repositories" below. The human decides if and when to
  upstream; you carry the fix here as a patch until then.

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

When touching `MODULE.bazel` or a `visibility`, also run
`bazelisk run //:public_surface`. It fails on a non-dev `bazel_dep`
nothing shipped uses, on a shipped file naming a dev-only repo, and on a
public target under `test/`; the docstring in `public_surface.py` is the
policy. CI runs it after lint.

## Bumping: the 30-day rolling window

`bazelisk run //:bump` supports `MODULE.bazel` files whose `bazel-orfs`
pin is **at most 30 days behind the commit being bumped to**, measured
between commit dates rather than against the clock. An older pin — or one
GitHub cannot date — is a hard stop, by design. Waiting does not clear it
and re-running does not change the verdict; only fixing the file does.

`bump.py` always downloads the newest `bump_impl.py`, so the bumper is
never stale; the only thing that can be out of date is the consumer's
file. When the check fires, fix the file, do not route around the check:

1. Re-seed `MODULE.bazel` from the template in `README.md` and re-apply
   the local edits, or
2. step the `bazel-orfs` commit forward ≤30 days at a time, re-running
   `//:bump` each step.

`--allow-stale-pin` exists for the human to decide to use. Do not reach
for it, edit `check_pin_window`, or change `BUMP_SUPPORT_WINDOW_DAYS` to
get a bump through — the migration paths for out-of-window shapes are
*deleted*, so a forced bump can leave `MODULE.bazel` half-rewritten.

The same window governs the bumper's own compatibility code: introduce a
migration branch with a `# COMPAT(YYYY-MM-DD)` marker naming the date the
old shape stopped being written, and delete the branch when it ages out.
`//:bump_compat_test` fails on a marker older than the window; the fix is
to delete the code, never to re-date the marker — and never to touch
`bump_reference_date.txt`, the commit-date anchor //:bump writes and the
test measures against. Full policy:
`docs/openroad.md`, "Supported window" and "Cleanup policy".

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


### Upstream repositories: moratorium on pull requests

Upstream repositories are **read-only for you** unless the human gives an
explicit order for a specific change. That covers every write: opening a
pull request or issue, commenting on one, pushing a branch to a fork in
preparation for one, any `gh api` write. It applies to ORFS, OpenROAD,
OpenSTA, yosys, the BCR and its modules, and every other repository that
is not bazel-orfs. A fix being correct, small, or obviously wanted is not
permission; neither is the fix having been carried here for a while.

When a fix is needed upstream, **carry it here as a patch**: a
`patches/00NN-orfs-*.patch` listed in `ORFS_PATCHES` (`orfs_source.bzl`)
for ORFS, the equivalent override mechanism for other modules. The patch
header says what it fixes, that it is not upstreamed, and how it retires
(the `//:bump` onto an upstream that carries the change). Carrying it
here is what proves the fix is needed and lets it churn where the churn is
cheap; the human prompts the upstream PR when the fix has settled and the
timing is right. Report carried patches as candidates for upstreaming;
do not act on them.

Within this repo, the Git policy above and the Confidentiality purge
still govern every push and PR. Use `gh api` writes here only for an
action that is already allowed, post-purge — never for merges, branch
protection, or repo administration.

## AI Guardrails

To prevent accidental destruction of the Bazel cache and state corruption,
both Claude Code and antigravity run the shared PreToolUse guard in
`.claude/hooks/guard_tool.py` — the single source of truth for these hard
stops. Antigravity reaches the same file through
`.agents/scripts/guard_tool.py`, so a rule can never be live for one agent
and missing for the other.

- `bazelisk clean` and `bazel clean` are blocked.
- Git operations (`checkout`, `switch`, `rebase`, `cherry-pick`, `merge`, `reset`, `pull`) on local `master` or `main` branches are blocked. Use remote-tracking branches or detached HEADs instead.
- `git push` to `master` or `main` is blocked; push a feature branch and open a pull request instead.
- Deleting, moving or force-updating a local `master`/`main` (`git branch -f/-D`, `git update-ref`, `git worktree add`) is blocked.
- Merging pull requests (`gh pr merge`, or a merge or branch-protection write through `gh api`) is blocked; merging is the human's call.
- Spelunking in `bazel-*` output directories and `.cache` using native tools (`grep`, `find`, `cat`) or agent file-reading tools is blocked to prevent context explosion.
- The use of the global `/tmp` directory is blocked. Always use a local `./tmp` directory for scratch work.

The list above is asserted equal to `guard_tool.py --explain` by
`//:guard_tool_test`, so it cannot drift from what is actually enforced.
