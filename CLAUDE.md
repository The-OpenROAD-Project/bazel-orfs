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

When touching a shell script, a `patch_cmds` entry, or a python file the
host interpreter runs, also run `bazelisk run //:host_tools`. Bazelisk is
the only thing a consumer must install; beyond it, nothing may be needed
that has not been on every supported Linux for a decade. It fails on a
denied tool (`jq`, `yq`, `perl`, `docker`, `cmake`, ...) in a shipped
script or `patch_cmds`, on an undeclared host-`python3` call site, and on
a host-run python file whose syntax floor is above 3.6 (RHEL 8, SLES 15);
the docstring in `host_tools.py` is the policy. CI runs it after
`//:public_surface`.

## Bumping

`bazelisk run //:bump` rewrites the override shapes it recognizes and
stops, naming the block, when it meets one it does not. It never writes a
partial file: `MODULE.bazel` is read once and written once at the end, so
a refusal leaves it byte-identical.

If a bump is refused because a block is unrecognized, fix the file — the
bumper does not carry migrations for old shapes. Re-seed `MODULE.bazel`
from the template in `README.md` and re-apply the local edits. `--ignore`
downgrades the refusal to a warning and updates only the parts the bumper
recognizes; the unrecognized block is left untouched.

`bump.py` always downloads the newest `bump_impl.py`, so the bumper is
never stale; the only thing that can be out of date is the consumer's
file. Details: `docs/openroad.md`, "Shapes the bumper recognizes".

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
- Building with CMake (`cmake`, `ccmake`, OpenROAD's `etc/Build.sh`) is blocked; bazel is the only build path.
- Git operations (`checkout`, `switch`, `rebase`, `cherry-pick`, `merge`, `reset`, `pull`) on local `master` or `main` branches are blocked. Use remote-tracking branches or detached HEADs instead.
- `git push` to `master` or `main` is blocked; push a feature branch and open a pull request instead.
- Deleting, moving or force-updating a local `master`/`main` (`git branch -f/-D`, `git update-ref`, `git worktree add`) is blocked.
- Merging pull requests (`gh pr merge`, or a merge or branch-protection write through `gh api`) is blocked; merging is the human's call.
- Spelunking in `bazel-*` output directories and `.cache` using native tools (`grep`, `find`, `cat`) or agent file-reading tools is blocked to prevent context explosion.
- The use of the global `/tmp` directory is blocked. Always use a local `./tmp` directory for scratch work. Narrowly exempted: an existing regular file of at most 64 KiB inside the agent's own `/tmp/claude-<uid>/` tree, so the hardcoded paths of bundled skill assets and session files stay reachable; the rest of `/tmp` stays blocked.

The list above is asserted equal to `guard_tool.py --explain` by
`//:guard_tool_test`, so it cannot drift from what is actually enforced.
