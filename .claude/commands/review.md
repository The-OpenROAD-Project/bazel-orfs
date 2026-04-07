Review changes since main for style, policy, and consistency in bazel-orfs.

## 1. Gather context

Run `git fetch origin` and check that the current branch is on top of `origin/main` (i.e., `origin/main` is an ancestor of HEAD). If not, warn the user that a rebase is needed before merging.

Review all uncommitted changes and any commits since main. Read the diff, changed files, and CLAUDE.md to understand project conventions.

## 2. Run linters and formatters

Run `bazelisk run //:fix_lint` to apply all project linters and formatters (buildifier, black, etc.) on changed files. Report any formatting changes made and fix any lint warnings.

## 3. Local validation (replicate CI locally, ~15s total)

Run these checks locally before reviewing style. They catch the most common CI failures and are much faster than waiting for remote CI (~10min round-trip). Run them in this order:

### 3a. Analysis check (~10s)

```sh
bazelisk build //... --nobuild
```

This runs full target analysis without building. Catches: conflicting actions (duplicate output paths from `orfs_flow` targets with same name+variant), missing deps, label errors, broken `select()` expressions.

### 3b. Fast targeted tests (~5s)

```sh
bazelisk test //test/bump:bump_test //test:lb_32x128_sky130hd_test //test/klayout:mock_klayout_test --test_output=errors
bazelisk build //test:lb_32x128_mock_openroad_floorplan
```

These exercise the mock openroad/klayout override paths and bump.sh logic cheaply.

### 3c. Check for .gitignore traps on new files

```sh
git check-ignore $(git ls-files --others --exclude-standard)
```

The repo has `bazel-*` in `.gitignore` which can silently ignore files with names starting with "bazel-" (e.g. fixture files). If any new files are ignored, either rename them or use `git add -f`.

Report any issues found. Do NOT proceed to style review if any of 3a-3d fail — fix them first.

## 4. Check Bazel conventions

For changed Bazel files, verify:

- **Rule usage**: correct rule types, proper attribute usage, no deprecated patterns
- **Visibility**: targets use the narrowest visibility that works
- **Naming**: target names follow existing conventions (snake_case, consistent prefixes)
- **Dependencies**: no unnecessary or circular dependencies
- **Labels**: use canonical label format, no hardcoded paths

## 5. Check consistency

- Do changed files follow the patterns of their neighbors?
- Are new files placed in the right location?
- Do naming conventions match existing files?
- Is anything duplicated that should be shared?
- Do new rules/macros follow the project's provider pattern (OrfsInfo, PdkInfo, etc.)?

## 6. Check for hacks and workarounds

Look for:
- Hardcoded paths or local-only workarounds
- Commented-out code or TODO comments without explanation
- Temporary workarounds that should be documented
- Files that look generated but were hand-edited

## 7. Security review

Scan changed files for common security concerns:

- **Unqualified PATH execution**: shell scripts or Bazel rules that run binaries from `PATH` without pinning (e.g., `exec klayout "$@"`). Flag these and check that the risk is documented.
- **Command injection**: shell scripts that interpolate variables into commands without quoting. Check for unquoted `$VAR` in command positions, `eval`, or backtick substitution with user-controlled input.
- **Credential exposure**: new files that contain or reference secrets, tokens, API keys, or `.env` files. Check that `.gitignore` excludes them.
- **Unsafe downloads**: `http_archive` or `http_file` rules without `sha256` checksums. New `urls` entries should always have a pinned hash.
- **Writable sandbox escapes**: `genrule` or `run_shell` actions that write outside `$@` or reference `$BUILD_WORKSPACE_DIRECTORY` in actions (as opposed to `bazel run` scripts where it is expected).
- **Overly broad visibility**: targets with `//visibility:public` that should be narrower.

For each finding, state the risk level (high/medium/low) and whether it is intentional or needs a fix.

## 8. Check documentation

For any changed `.md` files:
- Verify code examples are syntactically correct
- Check that internal links point to files that exist
- Ensure tone is welcoming and matter-of-fact

## 9. Summarize findings

Present findings as a numbered list of **concrete suggestions**, grouped by file. For each suggestion:

- State what's wrong or inconsistent
- Show what the existing code/docs do
- Give the specific fix (exact text or command to run)

Prioritize: policy violations > build breakage > missing content > style nits.

Order suggestions by **least churn first** — small, safe fixes before larger changes.

End with a short verdict: "Ready to merge", "Needs minor fixes", or "Needs significant work".

## 10. Offer to fix and clean up commits

After presenting findings, show a numbered menu combining both issues found and commit cleanup opportunities:

```
Actions available:
  [1] Fix: <description of issue 1>
  [2] Fix: <description of issue 2>
  ...
  [N] Restructure commits: split/squash into one-commit-per-concern
  [A] Apply all fixes
  [S] Skip
```

**Commit cleanup**: Review the current commit history since main. If any commit mixes unrelated concerns (e.g., a formatting fix bundled with a feature change, or a refactor mixed with a bug fix), offer to restructure into clean single-concern commits. Each commit should:

- Address exactly one logical change
- Have a clear, descriptive commit message
- Be self-contained and independently reviewable
- Follow CLAUDE.md conventions (e.g., `git commit -s`)

Wait for the user to pick items by number (e.g., "1, 3, N") before acting. Apply selected fixes one at a time, creating a clean commit for each.

ARGUMENTS: $ARGUMENTS
