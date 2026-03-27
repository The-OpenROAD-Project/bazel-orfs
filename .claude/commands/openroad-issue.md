> **Repo**: Spans TWO repos. Bazel builds, `bin/git-read`, and issue file creation happen in the openroad-demo root. Source reading, `git format-patch`, and `git am` happen in the upstream OpenROAD repo (`upstream/OpenROAD-flow-scripts/tools/OpenROAD`).

Create a copy-paste-ready GitHub issue for an OpenROAD bug.

The measure of an issue is how fast a developer goes from "I see this
in my queue" to "I have it reproducing under a debugger." An OpenROAD
developer triaging dozens of bugs from dozens of sources doesn't care
where it came from, why it crashes, or who introduced it. That's for
managers later. The developer wants: checkout origin/master, apply patch,
bazelisk test, observe failure, fire up debugger, fix, next.

Every step in this skill compresses the reproduction from gigabytes/hours
to kilobytes/seconds. That compression is the value. Don't bury it under
analysis.

ARGUMENTS: $ARGUMENTS

## Output format

A standalone .md file small enough to paste directly into a GitHub issue
body (GitHub has a ~65,536 character limit).

The issue reads top-down as an action sequence. At the top: apply this
patch to origin/master, run this bazelisk test, observe crash/hang/timeout.
Root cause and context come after, in plain prose.

Package the reproduction as a git format-patch that adds a failing bazel
test to the OpenROAD tree. The developer flow is:

    git am <patch>
    bazelisk test //src/<module>/test:<test_name>

If the reproduction is too large for a patch (>500 lines of test data),
attach it as a .tar.gz with a run-me script instead.

### Formatting rules

Write like you're talking to a colleague, not generating a report.

- No markdown headers (no ## or #) in the issue body. Blank lines separate sections.
- No bold, no italics.
- No tables (unless data is genuinely tabular and large).
- No `<details>` collapsible sections. Don't hide the patch.
- No Mermaid diagrams.
- Bare commit hashes — don't backtick them. GitHub auto-links 40-char SHAs.
- Permalinks for source references (https://github.com/The-OpenROAD-Project/OpenROAD/blob/<sha>/path#L42).
- Indented code blocks (4 spaces) for short commands. Fenced blocks only for the patch.
- No hard line wrapping in prose. Write long lines and let the browser wrap them.
  Hard wraps at 72/80 chars look like computer output and create ugly ragged text
  on narrow screens.
- Minimal visual noise. Every bold word, header, and formatting element makes the
  issue look more computer-generated and harder to scan.

### Issue template

The generated .md file follows this structure. Note: no headers, minimal formatting.

````
[<module>] <symptom in plain language>

Tested on origin/master <40-char-sha>.

Apply the patch at the bottom and run:

    bazelisk test //src/<module>/test:<test_name> --test_timeout=30

<what you'll observe: crash / hang / timeout / wrong output. No hard line wraps — let the browser wrap.>

    [ERROR XXX-NNNN] <exact error text, 1-3 lines>

<1-3 sentences of root cause in plain prose. No hard line wraps, no headers, no bold. Reference source with permalinks.>

<optional: additional context in plain prose.>

---

Reproducer (git am on origin/master <sha>):

```
<git format-patch for commit 1 — adds the failing test>
```

<if you have a clean fix, include it:>

Fix (git am on origin/master <sha>):

```
<git format-patch for commit 2 — fixes the bug, updates .ok>
```

<if not, replace the Fix section with prose:>

We tried <approach 1> and it broke <X tests> because <reason>.
We tried <approach 2> and it broke <Y tests> because <reason>.
The question that unblocks a fix: <specific question for the maintainer>.
````

Title format: `[module] symptom in plain language` — matches OpenROAD convention.

## Workflow

### 1. Understand the bug

Read the error message, logs, and context. Use the Grep tool to search
`upstream/OpenROAD-flow-scripts/tools/OpenROAD/src/` for the error string
to understand:
- What code path produces it
- What conditions trigger it
- What the intended behavior is

### 2. Create or find reproduction

If a reproduction already exists (e.g. bug.tar.gz, failing bazel build):
- Download/extract it
- Verify it reproduces on latest OpenROAD

If not, use substep targets to isolate and run the failing substep.

#### Substep targets (preferred)

Enable substep targets in the BUILD by passing `substeps = True` to
`orfs_flow()` (or the demo wrapper that calls it — `demo_flow()`,
`demo_sram()`, `demo_hierarchical()` all accept `substeps`):

```starlark
demo_hierarchical(
    name = "MeshWithDelays",
    substeps = True,
    ...
)
```

This generates run targets for individual substeps within each stage.
The naming convention is `<module>_<stage>_<substep>`:

| Stage | Substeps |
|-------|----------|
| floorplan | `2_1_floorplan`, `2_2_floorplan_macro`, `2_3_floorplan_tapcell`, `2_4_floorplan_pdn` |
| place | `3_1_place_gp_skip_io`, `3_2_place_iop`, `3_3_place_gp`, `3_4_place_resized`, `3_5_place_dp` |
| cts | `4_1_cts` |
| route | `5_1_grt`, `5_2_route`, `5_3_fillcell` |

Each substep target depends on its parent stage via `src`. `bazelisk build`
caches the parent stage's artifacts; `bazelisk run` deploys them and runs
a single `make do-<substep>` target.

Within a stage, substeps share a mutable ODB in the deploy directory.
Each substep reads the ODB left by the previous one. So to run substep N,
you must first run substeps 1 through N-1 in order:

- For the first substep (e.g. `2_1_floorplan`): use `_deps` to deploy
  the previous stage's artifacts, since variables are stage-specific.
- For subsequent substeps (e.g. `2_2_floorplan_macro`): just run the
  previous substep first — bazel caches the build, so only the deploy
  + make execution happens.

```bash
# Example: reproduce a macro placement failure (substep 2_2)
# Step 1: run substep 2_1 first (deploys synth artifacts + runs initial floorplan)
bazelisk run //gemmini_8x8_abutted:MeshWithDelays_floorplan_2_1_floorplan
# Step 2: now run substep 2_2 (reads the ODB written by 2_1)
bazelisk run //gemmini_8x8_abutted:MeshWithDelays_floorplan_2_2_floorplan_macro
```

#### Generating the reproducer archive (fallback)

When substep targets aren't available or you need a self-contained archive,
deploy `_deps` and use `make <script>_issue`:
```bash
bazelisk run //<project>:<module>_<stage>_deps
tmp/<project>/<module>_<stage>_deps/make <script>_issue
# e.g. make macro_place_issue, cts_issue, detail_route_issue, etc.
```

Manual approach (when `make <script>_issue` doesn't cover the case):
- Start from the failing stage's .odb (from `_deps` or `bazel-bin/`)
- Write a `bug.tcl` that loads the ODB and runs the failing command
- Note which earlier step created the bad state (chain of evidence)

### 3. Build OpenROAD from source and test on origin/master

```bash
cd upstream/OpenROAD-flow-scripts/tools/OpenROAD
git fetch origin && git checkout origin/master
git submodule update --init --recursive
bazelisk build //:openroad
```

Binary at `bazel-bin/openroad`. Incremental rebuilds of a single module
(e.g. `src/drt/`) take < 5 minutes.

Record the full 40-char SHA:
```bash
bin/git-read upstream/OpenROAD-flow-scripts/tools/OpenROAD rev-parse HEAD
```

Verify the bug reproduces at this exact commit before proceeding.

### 4. Whittle the .odb

Use `whittle.py` to minimize the design while preserving the error:

```bash
# Use pipefail + tee so you can monitor progress with: tail -f whittle.log
# The --step command also benefits from tee for monitoring each iteration:
set -o pipefail
python3 upstream/OpenROAD-flow-scripts/tools/OpenROAD/etc/whittle.py \
  --base_db_path input.odb \
  --error_string "<ERROR_STRING>" \
  --step "bash -o pipefail -c '<OPENROAD_PATH> -no_init -threads 1 -exit bug.tcl 2>&1 | tee step.log'" \
  --persistence 4 \
  --use_stdout \
  --dump_def 2>&1 | tee whittle.log
```

Monitor progress: `tail -f whittle.log` (whittle) or `tail -f step.log` (each step).

Whittling tips:
- Start with moderate persistence (3-4), not max (6). Watch progress —
  if you see futile iterations, stop and take your winnings.
- Watch for diminishing returns: if hundreds of iterations with no size
  reduction, the remaining instances are all needed. Move on to LEF/LIB.
- Adjust persistence to the problem: 1M-cell design benefits from
  persistence 6. A 1K-cell design doesn't need more than 3.
- Re-whittle the result: a second pass sometimes finds further reductions.

Critical whittle.py notes:
- `openroad` must be on PATH (whittle uses it internally to read ODB counts).
  Use `PATH="$(pwd)/bazel-bin:$PATH"` — never install to `~/.local/bin/`.
- Use absolute paths for `--base_db_path` and in `--step` (whittle changes cwd)
- Don't pipe whittle output through `tail` — use `tee` with `pipefail`
- Use `--use_stdout` when errors go to stdout (not just stderr)
- `chmod u+w *.odb` first (bazel outputs are read-only)
- Whittle renames the input ODB to `whittle_base_original_<name>.odb`
- Result at `whittle_base_result_<name>.odb`
- `--dump_def` produces DEF files alongside ODB at each step
- The `--step` command must exit nonzero AND contain the error string

Don't lose the intent of the bug when whittling. The goal is not the
smallest case that outputs the error string — it's the smallest case that
reproduces the idiomatic problem. If the original bug is "OBS covers
pin at die edge", the whittled case must still have that OBS/pin geometry.
Verify after whittling that the root cause is the same.

### 5. Convert .odb to .def

DEF is text and can go in the patch. Write a Tcl script:

```tcl
read_lef platform.lef
read_db whittled.odb
write_def whittled.def
```

### 6. Minimize LEF/LIB dependencies

Read the OpenROAD source code to understand what the failing command
actually parses — don't guess. Use Grep to search the source for field names
to know which LEF sections are required vs optional.

1. List cells remaining in the whittled DEF
2. Extract only those MACRO definitions from the cell LEF
3. Extract only the LAYER/VIA/VIARULE sections actually used
4. Strip LIB entirely if the failing command doesn't need timing
5. Test after each removal — binary search for what's needed

Goal: each file is tens of lines, not thousands.

### 7. Rebuild bug.tcl with text files

```tcl
read_lef platform_minimal.lef
read_lef macro_minimal.lef  ;# if needed
read_def whittled.def
# ... the command(s) that trigger the error
```

Verify the error still reproduces with minimal files.

### 8a. Package the reproducer as a patch

This is the minimum shippable unit. Instead of loose files and inline
analysis, create a git format-patch that a developer can apply and run.

In the OpenROAD worktree (at origin/master), create test files under
`src/<module>/test/`:
- Minimal LEF, DEF, and/or liberty files
- A test Tcl script (e.g. `obs_covers_pin.tcl`)
- A .ok file (expected output — include the error if the test
  demonstrates a bug via `catch`)
- A test entry in `src/<module>/test/BUILD`

Verify: `bazelisk test //src/<module>/test:<test_name> --test_output=streamed`

Commit, then `git format-patch origin/master`. This is the reproducer
patch. A reproducer-only issue is valuable — don't block on a fix.

If the reproduction can't fit in a bazel test (needs external PDK, huge
design, multi-step flow), fall back to a .tar.gz with a run-me script.
But always try the patch approach first.

#### Preserve exploration findings

Creating the test requires deep exploration of the module's test
infrastructure: BUILD macros, resource patterns, golden-output
conventions, grid constants, safe vs unsafe call sites. This knowledge
is expensive to acquire and ephemeral if left only in conversation
context or plan files.

Preserve it where future runs (yours or a developer's) can find it
without spelunking. Think Hitchhiker's Guide: "on display in the
bottom of a locked filing cabinet stuck in a disused lavatory with a
sign on the door saying 'Beware of the Leopard.'" Don't be the
Vogons. Put information where people actually look.

Good places (durable, discoverable):

- **Code comments**: when the fix has a non-obvious reason (e.g.
  "skip orientation adjustment rather than assert — BLOCK macros
  legitimately have no site in the row map"), put it in the code.
- **Issue body**: the root-cause prose section is the right place
  for architectural context ("getSiteOrientation returns nullopt
  when row_sites_ at (x,y) has no entry for the cell's site —
  this happens with multi-height cells whose site differs from
  the single-height rows").
- **Commit message**: include the key facts that informed the fix.
  "5 call sites use .value(); 3 others already check the optional"
  saves the next person from re-auditing.

Bad places (ephemeral, unsearchable):

- **Git PR comments / review comments**: disappear into closed PR
  history. Nobody searches there. The conversation dies with the PR.
- **Plan files / conversation context / memory**: not on origin/master.
  Gone when the session ends or the plan file is cleaned up.
- **Slack / email threads**: even worse. Not version-controlled at all.

### 8b. Add a fix (optional)

If you have a clean fix, add it as a second commit:
1. Fix the bug in the source code
2. Update the .ok file if the test now produces different output
3. Verify: `bazelisk test //src/<module>/test:<test_name>` passes
4. Run related existing tests to check for regressions

Generate patches: `git format-patch origin/master` produces one file per
commit. Include each as its own fenced code block in the issue.

If the fix isn't clean (breaks other tests), don't include it. Instead,
describe what you tried and what broke in the issue prose. A reproducer
with a clear question for the maintainer gets faster responses than a
reproducer alone.

### 8c. Constraint test (before committing to a fix)

Before finalizing a fix, write a second test that PASSES on clean master
and exercises the same code path. This constrains the fix — if the fix
breaks this test, the fix is too broad.

The fastest way to compare: `git stash`, run the constraint test (should
pass), `git stash pop`, run again (should still pass).

When debugging test failures, use `--test_output=streamed` (one test at a
time, output inline) or `--test_output=all` (batch, output after). Never
dig through the bazel cache/sandbox for test logs.

### 9. Collect versions and research

Use the SHA recorded in step 3 (bare, not backticked — GitHub auto-links it).

Use `bin/git-read <dir> <subcmd>` for git operations in upstream repos.
This matches the `Bash(bin/git-read:*)` permission and only allows
read-only git subcommands.

Research the affected code area:
- Use `bin/git-read <upstream-repo> log --oneline -- <src-dir>` to find recent activity
- Search for related open issues/PRs
- Build permalinks to the relevant source lines using the SHA

### 10. Generate the .md issue file

Follow the template from "Issue template" above. Remember:
- Don't bury the lead. First thing after the title: origin/master hash,
  then apply patch, then run test, then observe failure.
- The reproducer patch is always included. The fix patch is a bonus —
  include it if it's clean, omit it if it breaks other tests.
- If the fix isn't clean, include prose analysis of what was tried,
  what broke, and the specific question that unblocks a fix. A
  reproducer with a clear question gets faster responses than a
  reproducer alone.
- Root cause in plain prose below. No headers. No hard line wraps.
- The patch goes at the bottom (it's the longest part).
- Write like you're leaving a note for a colleague, not a report for a committee.

### 11. Debug with gdb (optional)

Only if recompilation of the affected module takes < 5 minutes:

```bash
cd upstream/OpenROAD-flow-scripts/tools/OpenROAD
# Edit source
bazelisk build //:openroad  # incremental rebuild
# Run under gdb
gdb --args bazel-bin/openroad -no_init -threads 1 -exit bug.tcl
```

### 12. Optimize for fix time

The goal isn't just to file — it's to get the bug fixed fast. Use `gh`
and `git log` data to understand who maintains the affected module, how
fast they respond, and what makes them act.

```bash
# Who commits to this module?
git log --format="%an" -50 -- src/<module>/src/ | sort | uniq -c | sort -rn
# How fast do they close issues?
gh api "repos/The-OpenROAD-Project/OpenROAD/issues?state=closed&per_page=10" \
  -q '.[] | select(.title | test("\\[<module>\\]")) |
  "\(.assignees | map(.login) | join(",")) \(.created_at[:10]) \(.closed_at[:10])"'
# What are they working on now?
gh pr list --repo The-OpenROAD-Project/OpenROAD --search "<module>" --json number,title,author
```

Levers that reduce time-to-fix:

- **Issue with patch > PR**: issues with patches don't clog CI. The
  maintainer integrates it on their terms, in their CI workflow,
  alongside their other changes. PRs force you to babysit CI — linting,
  formatting, regression runs you didn't break. Feature requests don't
  clog CI either.
- **Complete patch > reproducer-only**: a maintainer can review+merge
  instead of investigate+fix. Cuts turnaround from days to hours.
- **C++ unit test > Tcl regression test**: faster iteration, smaller
  blast radius, easier to review. No LEF/DEF/LIB platform deps.
- **Fast-compiling test**: extract the code under test into a focused
  cc_library so the test compiles in seconds. This nerd-snipes
  build-system-minded maintainers — they see the 5-second compile and
  want to apply the pattern across the codebase.
- **@mention the right people**: check who self-assigns, who responds
  fast, who owns the code. A terse mention ("Patch included with unit
  test") is enough — the issue body has the details.
- **Align with ongoing work**: if the maintainer has open PRs touching
  the same area, reference them. Your fix might get absorbed.

### 13. Security review and handoff

NEVER push or post automatically. The user pushes and posts.

Before handing off to the user, review what you're about to publish:

- No absolute paths from the local machine (e.g. /home/username/...)
- No private repository URLs (internal repos)
- No credentials, tokens, or API keys
- No private email addresses beyond what's already public in git history
- No internal project names or codenames that aren't public
- References only to public issues (e.g. The-OpenROAD-Project/OpenROAD#9862,
  not Org/secretrepo#172)
- Patch files don't contain paths or content from private repos

Save the issue .md emphemral file to tmp/ for the user to review:

```bash
cp issue.md docs/issues/<slug>.md
```

The user decides when and how to post.

### 14. Unblock yourself with the fix

Filing quality issues isn't charity — it's self-interest with a time
horizon. Every bug you patch locally but don't report upstream becomes
technical debt that compounds. You'll hit a real problem you can't
patch around at the worst possible moment. The clock is always ticking.
Take the time to report the fix.

Once the issue is filed, apply the same patch to your own build.

BLOCKER (as of March 2026): building OpenROAD from source as a
downstream consumer is broken by dev_dependency leaks in OpenROAD's
MODULE.bazel (rules_chisel, npm, toolchains_llvm extensions not
guarded). PR #9827 fixes this. Until it merges, the source-build
workflow below does NOT work. Use the manual workaround (e.g.
MACRO_PLACEMENT_TCL) instead, and wait for the fix to land in Docker.

When #9827 merges, the workflow is:

1. **Check disk cache first.** Building OpenROAD from source without
   a shared disk cache means a full 30+ minute rebuild every time.
   Check that `user.bazelrc` or `.bazelrc` has:
   ```
   build --disk_cache=/path/to/.bazel-disk-cache
   ```
   See CLAUDE.md "Shared bazel disk cache". Without it, recompilation hell.

2. Uncomment the `bazel_dep(name = "openroad")` block in MODULE.bazel.
   Set the commit, add your fix patch, and set `openroad = "@openroad//:openroad"`
   in `orfs.default()`:
   ```starlark
   orfs.default(
       image = "...",
       sha256 = "...",
       openroad = "@openroad//:openroad",
   )
   ```
   Note: patches in `git_override` must be from the root module
   (`//patches:foo.patch`), not from `@bazel-orfs//`.

3. `bazelisk build` your design — it now uses the fixed OpenROAD.

4. When the fix lands upstream and the Docker image updates:
   ```bash
   bazelisk run @bazel-orfs//:bump
   ```
   Remove the source override + `openroad` arg. Back to Docker.

See: https://github.com/The-OpenROAD-Project/bazel-orfs/blob/main/docs/openroad.md

## Checklist

Before posting, verify:
- [ ] Tested against latest origin/master (bare SHA in issue body)
- [ ] Patch applies cleanly with git am
- [ ] `bazelisk test` command reproduces the failure
- [ ] Reproduces with -threads 1 (deterministic)
- [ ] No absolute paths in patch or test files
- [ ] No environment variable dependencies
- [ ] All files are text (no binary .odb)
- [ ] Test runs/fails in < 30 seconds
- [ ] Issue body < 60K characters
- [ ] No markdown headers, bold, tables, or collapsible sections in issue body
- [ ] Bare commit hashes (no backticks)

### Build graph for unit tests

Unit tests must compile in seconds, not minutes. If a cc_test depends
on a monolithic module library (e.g. `//src/mpl`), extract the code
under test into a focused cc_library with minimal deps (typically just
odb + utl).

Signs a test needs this treatment:
- `features = ["-layering_check"]` in the BUILD — means it includes
  private headers and the dep graph is wrong
- deps list includes `//src/<module>` (the whole module)
- test takes minutes to compile on a cold cache

The fix:
1. Extract the class under test into `<Class>.h` / `<Class>.cpp`
2. Add `cc_library(name = "<class>")` with only the needed deps
3. Point the cc_test at `//src/<module>:<class>` instead of `//src/<module>`
4. Qualify message IDs (`utl::MPL` not bare `MPL`) since you're
   outside the module's namespace-level using declarations

Prefer C++ unit tests over Tcl/LEF/DEF regression tests — they're
smaller, faster, and prove the fix at the API level.
