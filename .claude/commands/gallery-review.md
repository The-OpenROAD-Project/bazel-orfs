> **Repo**: Reviews the openroad-demo repo by default. If cwd is in an upstream/ subdirectory, `cd` to the openroad-demo root first. If the user explicitly wants to review upstream changes, adapt to that repo's git history instead.

Review changes since main for style, policy, and consistency. If demo projects were added or modified, delegate to `/demo-review` for demo-specific checks.

## 1. Gather context

Review all uncommitted changes and any commits since main. Read the diff,
changed files, and the top-level README.md to understand project conventions.

**Branch protection is enabled on `main`** — all changes must go through
a pull request. Direct pushes to `main` are blocked. Create a feature
branch for reviewed changes. **Do not run `gh pr create`** — the human
creates PRs.

## 2. Determine scope

Check whether the diff touches any demo project directories (e.g., `serv/`, `vlsiffra/`, `gemmini/`, or a new `<project>/BUILD.bazel`).

- **If demo projects were added or modified**: run `/demo-review` for the full demo-specific checklist (README structure, BUILD.bazel style, constraints.sdc, MODULE.bazel, gallery table, build_times.yaml). Continue with the generic checks below for any non-demo files in the diff.
- **If no demo projects were touched**: skip `/demo-review` and apply only the generic checks below.

## 3. Check tone and language

All `.md` files should use a **welcoming, matter-of-fact tone**. Flag language that is:

- **Condescending or patronizing**: e.g., "easy", "simply", "just", "teaches students", "sense of accomplishment"
- **Dismissive**: e.g., "stand back and watch", "no-spam check", implying contributors need hand-holding
- **Lecturing**: telling people what they should learn or feel, rather than describing what the project does
- **Harsh or gatekeeping**: language that makes contributors feel unwelcome

The writing should respect the reader's intelligence. Describe what things are and how they work; don't tell people what to think or feel about them. When in doubt, prefer neutral and direct over cheerful or instructional.

## 4. Check for hacks and workarounds

Look for:
- Hardcoded paths or local-only workarounds
- Files that look like they were generated but hand-edited
- Commented-out code or TODO comments that belong in a "Future Improvements" section
- Temporary workarounds without explanation

## 5. Check consistency

- Do changed files follow the patterns of their neighbors?
- Are new files placed in the right location?
- Do naming conventions match existing files?
- Is anything duplicated that should be shared?

## 6. Fact-check claims

For any factual claims in changed `.md` files — frequencies, cell counts, authorship, publication dates, project descriptions, external references — verify against the web and relevant literature. In particular:

- **Upstream project descriptions**: check that the description matches what the project actually is (e.g., correct ISA, correct algorithm, correct author/org)
- **Reported frequencies or metrics**: cross-reference against the upstream README, papers, or published benchmarks
- **Citations and quotes**: confirm the source actually says what's attributed to it (fetch the URL and check)

Flag any claims that can't be verified or that contradict published information.

## 7. Check links

Fetch every external URL in changed `.md` files and verify:

- The URL is reachable (not 404, not redirecting to an unrelated page)
- The linked page matches what's described (e.g., a "GitHub repo" link actually points to a repo, not an issue or PR)
- Internal links (`[text](file.md)`, `[text](path/)`) point to files that exist in the repo
- Anchor links (`#section`) point to headings that exist in the target file

## 8. Check for duplicates and originality

- **Duplicate projects**: check whether the design being added overlaps with or is a variant of a project already in the gallery. List any similar projects and explain the overlap (e.g., same upstream repo, same core with different config, same algorithm family). Not all overlaps are problems — but they should be called out so the contributor can justify the addition.
- **Plagiarism**: check that README descriptions, "What This Demo Builds" text, and other prose are original and not copied from upstream READMEs, papers, or other sources without attribution. Brief factual statements (ISA, cell counts) don't need attribution, but copied paragraphs do.
- **Similar external projects**: search the web for other OpenROAD/ORFS configurations of the same design. If someone has already published an ORFS flow for this project (e.g., in OpenROAD-flow-scripts, a fork, or a paper), link to it — the contributor should be aware and can reference or build on that work.

## 9. Summarize findings

Present findings as a numbered list of **concrete suggestions**, grouped by file. For each suggestion:

- State what's wrong or inconsistent
- Show what the existing code/docs do
- Give the specific fix (exact text or command to run)

Prioritize: policy violations > missing content > style nits.

Order suggestions by **least churn first** — small, safe fixes before larger changes.

End with a short verdict: "Ready to merge", "Needs minor fixes", or "Needs significant work".

## 10. Offer to fix

After presenting findings, ask the user if they'd like you to fix the issues. If yes, apply fixes **one commit per concern**, starting with the least-churn fix first. Each commit should be self-contained and reviewable on its own.

ARGUMENTS: $ARGUMENTS
