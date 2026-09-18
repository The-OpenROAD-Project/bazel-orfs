> **Repo**: Applies wherever `gh`, the GitHub API or GitHub Actions are used from this workspace, including writes to other repositories when those are explicitly ordered.

Do not use GitHub features that GitHub has sunset or deprecated, and route around them when a tool still touches one. Every item below has bitten a real session or a real CI run; the fix next to it is the one to use.

ARGUMENTS: $ARGUMENTS

## Rule

1. A `gh` command that fails with a deprecation or sunset notice has done nothing: check before retrying (`gh pr view`, `gh api ... --jq .body`), then do the same write through the REST endpoint with `gh api`, which pins the API version.
2. Never opt back in to a sunset feature to make a command succeed (no preview `Accept` headers, no classic projects, no legacy runners).
3. When a new deprecation shows up, add it to the list below in the same change that works around it, with the error text or announcement and the replacement.

## Known deprecations and what to use instead

### `gh` and the API

| deprecated | symptom | use instead |
|---|---|---|
| Projects (classic), `projectCards` on issues and PRs | `gh pr edit` / `gh issue edit` fail with `GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)` and leave the body unchanged (seen 2026-09-18 on `gh pr edit --body-file`) | `gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -F body=@file` (issues: `.../issues/<n>`); Projects v2 through `gh project` if a project is really wanted |
| GraphQL `PullRequest.timeline`, `Issue.timeline` | field removed | `timelineItems` |
| GraphQL and REST preview media types (`application/vnd.github.<name>-preview+json`) | headers ignored or rejected | plain `application/vnd.github+json` with `X-GitHub-Api-Version: 2022-11-28` (what `gh api` sends) |
| Legacy Teams API by team id (`/teams/{team_id}/...`) | 404 or deprecation header | org-scoped paths `/orgs/{org}/teams/{team_slug}/...` |
| Team discussions API | removed | GitHub Discussions |
| `docker.pkg.github.com` (GitHub Packages Docker registry) | sunset | `ghcr.io` |
| Password authentication for git over HTTPS | rejected | `gh auth login` token or SSH |
| `git://github.com/...` protocol | connection refused | `https://` or `ssh://` |
| Subversion access to GitHub repositories (`git svn`, `svn checkout`) | sunset January 2024 | git |
| Personal access tokens (classic) for new automation | still accepted, being steered away from | fine-grained tokens scoped to the repo |

### GitHub Actions

| deprecated | symptom | use instead |
|---|---|---|
| `::set-output`, `::save-state`, `::set-env`, `::add-path` workflow commands | warning, then ignored | `$GITHUB_OUTPUT`, `$GITHUB_STATE`, `$GITHUB_ENV`, `$GITHUB_PATH` |
| Node 12 and Node 16 actions (`actions/checkout@v2`/`@v3`, `actions/cache@v2`/`@v3`, `setup-python@v2`/`@v4`, `upload-artifact@v3`, `download-artifact@v3`) | runner warnings, then refusal; `upload-artifact@v3` stopped working January 2025 | current majors (`actions/checkout@v7`, `actions/cache@v6`, `upload-artifact@v4` or later); Node 20 actions are the next to go in favour of Node 24, so keep majors current at each CI touch |
| Runner images `ubuntu-18.04`, `ubuntu-20.04`, `macos-11`, `macos-12`, `windows-2019` | job never schedules or fails at startup | `ubuntu-22.04` or `ubuntu-24.04` (this repo uses `ubuntu-22.04`; `ubuntu-latest` now means 24.04, do not assume it is stable) |
| `actions/create-release`, `actions/upload-release-asset` (archived) | unmaintained, Node 12 | `gh release create` / `gh release upload` in a `run:` step |

### Status of this repo (checked 2026-09-18)

`.github/workflows/ci.yml`: `actions/checkout@v7`, `actions/cache/{save,restore}@v6`, `bazel-contrib/setup-bazel@0.19.0`, `runs-on: ubuntu-22.04`. Nothing on the list above. `jlumbroso/free-disk-space@main` floats; pin it when it is next touched.
