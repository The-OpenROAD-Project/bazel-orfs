> **Repo**: Run from the openroad-demo root.

Upgrade a demo project to the latest upstream version.

Finds the most recent commit on the project's default branch, updates
`MODULE.bazel` with the new commit hash and sha256, then rebuilds and
refreshes metrics.

## 1. Find the current version

Read `MODULE.bazel` and find the `http_archive` for `<project>`. Extract:
- The current commit hash from the `urls` field
- The GitHub owner/repo from the URL

## 2. Find the latest commit

```bash
# Get the latest commit hash from the default branch
curl -sL "https://api.github.com/repos/<owner>/<repo>/commits?per_page=1" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['sha'])"
```

If the latest commit matches the current one, report "already up to date" and stop.

## 3. Update MODULE.bazel

Compute the new sha256:
```bash
curl -sL "https://github.com/<owner>/<repo>/archive/<new_commit>.tar.gz" | sha256sum
```

Update the `http_archive` entry in `MODULE.bazel`:
- `sha256` → new hash
- `strip_prefix` → `<repo>-<new_commit>`
- `urls` → new archive URL

## 4. Check for patch compatibility

If the project has `patches` in its `http_archive`, the patches may not apply
cleanly to the new version. Run a quick build test:

```bash
bazelisk build //<project>:<top_module>_synth 2>&1 | tail -20
```

If patches fail, update them:
1. Download the new source
2. Re-apply the fix manually
3. Regenerate the patch file in `<project>/patches/`

## 5. Rebuild with /demo-debug

Use `/demo-debug <project>` to build through all stages, fixing any new issues.

## 6. Update metrics with /demo-update

Use `/demo-update <project>` to extract fresh metrics, update READMEs, and
regenerate the gallery screenshot.

## 7. Commit

Commit the changes with a message like:
```
Upgrade <project> to <short_hash>
```

ARGUMENTS: $ARGUMENTS
