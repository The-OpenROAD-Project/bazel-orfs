> **Repo**: Run from the bazel-orfs root, with a clone of the upstream repository (OpenROAD, ORFS, ...) in `tmp/`. Applies only once the human has ordered the upstream pull request; until then the change is a carried patch (CLAUDE.md, "Upstream repositories").

How a fix carried here as patches becomes an upstream pull request a maintainer can review. The carried patches churned where churn was cheap; the pull request is the settled change, told to someone who has never seen bazel-orfs.

ARGUMENTS: $ARGUMENTS

## 1. One commit per concern

A carried series records the order things were found in: a feature, a fix to it, a lint fix, another fix. The pull request records the concerns: one commit each, each building and passing its own tests, in an order where each one only adds.

Build the series from snapshots rather than by rebasing the history: on a fresh branch off upstream's tip, for each concern, check out the final state of the files that concern owns (`git checkout <final> -- <paths>`, or an edit of a shared file down to that concern's part) and commit. The last commit's tree must equal the final tree; `git diff <final> HEAD` empty is the check. Then run each commit's own tests at that commit.

Ordered by the human as one pull request per concern, the series is split across pull requests; a pull request that needs another's unmerged change says so and stays a draft (`dogfooding`, rule 6).

## 2. Written for the upstream reader

Commit messages and the pull request body say what the change does and why, in upstream's terms. Scrub the bazel-orfs bookkeeping: carried patch numbers, "carried", ladder rows, our branch names, the order things were found in. One link to the bazel-orfs pull request that is the integration test is enough context.

The body leads with the number: what the change buys, measured, in a table if there are several designs. Then one line per commit. Then what the tests check.

The tests check intended behaviour, not golden output (`dogfooding`, rule 5); a new `.ok` or `.defok` is a review comment waiting to happen.

## 3. Upstream's lint, at upstream's versions

Lint with the versions upstream's CI pins, not the ones installed here: a different `clang-format` or `black` reformats lines the change never touched, and CI fails on them. Read the version from upstream's CI configuration and install it in a venv under `tmp/`. When this skill was written: OpenROAD, `clang-format` 18 and `tclint` 0.7.0; ORFS, `black` 26.5.1 and `tclint`/`tclfmt` 0.7.0.

Generated files equal their generator's output. ORFS's variable documentation is generated from `variables.yaml`; run the generator, and when it also rewrites drift unrelated to the change, put only the change's part in by hand so the diff stays the change's.

Lint every commit, not only the last: a series where commit 2 fixes commit 1's lint is two concerns, one of them noise.

## 4. Draft first, and force-push only while it is a draft

Open the pull request as a draft. Correctness evidence that takes hours can come after it is opened; it may fail, and a draft says that is possible.

While it is a draft, rewrite freely and force-push: squash, reorder, fix commits in place, so the series stays one commit per concern. Once the human marks it ready for review, stop: new commits only, fast-forward pushes, so a reviewer's comments stay attached to what they read.

## 5. Bot review: verify, answer, resolve

A review bot's comments (Gemini Code Assist, for one) are claims to verify, not instructions. For each one:

- check it against the code: does the problem exist, does the suggestion fix it, does it hold for every caller;
- reject a suggestion that turns a hard failure into a silent fallback (a quashed null, a default that hides a missing input): the change fails early and loudly on purpose;
- take it, in the commit that owns the concern, or don't;
- reply on the thread, "Taken: <what changed>" or "Not taken: <why>", and resolve it.

Every thread answered and resolved, so the human reviewer sees none open that nobody looked at.

## 6. The carried patch stays put while the pull request settles

Review changes the pull request: a bot's nit, a maintainer's question, a rename. Do not mirror each round into the carried patch. An edit to a file in `patches/` changes the key of every stage that takes the patched tree, so it costs every consumer a rebuild (`cache-miss`), and the patch retires anyway at the `//:bump` onto the merged pull request, which brings whatever review settled on. Until that bump, the patch keeps what it carried and its header points at the pull request.

Update it before then only for an urgent need: the carried version breaks a build here or gives a wrong result, and waiting for the merge costs more than the churn. That update is a fix in its own right, with the reason in the patch header, not a sync with the review.
