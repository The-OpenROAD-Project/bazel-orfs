# Contributing to the OpenROAD Demo Gallery

**Pull requests adding demo projects are welcome!**

## Adding a New Project

Adding a project with Claude Code:

```
/demo-add <github-url>
```

Claude will research the project, pick the right top-level module, set up
Bazel build targets, run synthesis, generate a placement screenshot, and
update the gallery — all in one go.

The strategy is **early results, fast iterations**: get a working placement
image in minutes using aggressive speed defaults, then refine toward a
polished routed design. See the full guide:
**[Adding Projects](docs/adding-projects.md)**.

No source code is copied. The entire project stays tiny — just text and patches.

## Try OpenROAD on Your Own Project

If you'd like to try OpenROAD on your private project, point Claude Code at this
repository and tell it to use the best practices here to create an initial Bazel
configuration and README for your project. The skills and patterns in this repo
encode real experience with the ORFS flow.

## Claude Code Skills

The Claude skills (`/bump-orfs`, `/demo-add`, `/demo-debug`, `/demo-pr`,
`/demo-progress`, `/demo-review`, `/demo-update`, `/demo-upgrade`, `/fix-errors`)
have been tuned while adding projects to the gallery, embedding real experience
with Bazel and OpenROAD into each skill so they get smarter over time.

| Skill | Description |
|-------|-------------|
| `/demo-add <url>` | Add a new project to the gallery |
| `/demo-debug <project>` | Build incrementally through each ORFS stage, fixing errors |
| `/demo-update <project>` | Refresh metrics, screenshots, and gallery table |
| `/demo-review` | Review changes for style and policy consistency |
| `/demo-pr` | Re-test all affected projects before merging |
| `/demo-upgrade <project>` | Upgrade to latest upstream version |
| `/demo-progress` | Monitor a running build |
| `/bump-orfs` | Bump bazel-orfs and ORFS Docker image |
| `/fix-errors` | Analyze and fix build errors |

## Typical Workflow

1. **Add or modify** a project: `/demo-add <url>` or edit `BUILD.bazel`/`constraints.sdc`
2. **Build incrementally**: `/demo-debug <project>` — fixes errors at each stage
3. **Update metrics**: `/demo-update <project>` — refreshes tables, screenshots, build times
4. **Self-review**: `/demo-review` — checks style, policy, consistency with other projects
5. **Pre-merge test**: `/demo-pr` — re-tests all affected projects, flags regressions

## Testing Without CI

This project is CI-less. Instead, use `/demo-pr` before merging:

```
/demo-pr
```

Claude will re-build and re-test all affected projects, update the Projects table
with fresh metrics, and verify nothing regressed. Use this when:
- **Refactoring** shared config (`defs.bzl`, `MODULE.bazel`): `/demo-pr` re-tests
  affected projects and updates their table rows. Push the refactoring as a separate PR.
- **Adding a new project**: `/demo-add` adds it, then `/demo-pr` verifies the full gallery.
- **Bumping ORFS**: `/bump-orfs` updates the image, then `/demo-pr` rebuilds everything
  and updates the "Built with" column.

`/demo-update <project>` updates the "Built with" column and metrics for a single project.

## Utility Scripts

All scripts run via `bazelisk run` — no local Python or tool installation needed:

| Script | Usage | Description |
|--------|-------|-------------|
| `build_times` | `bazelisk run //scripts:build_times -- <project>` | Extract per-stage build times to `build_times.yaml` |
| `build_time_chart` | `bazelisk run //scripts:build_time_chart` | Render build time chart from `build_times.yaml` |
| `extract_metrics` | `bazelisk run //scripts:extract_metrics -- <logs> <reports>` | Extract frequency, cells, area, WNS from ORFS output |
| `update_readme` | `bazelisk run //scripts:update_readme -- ...` | Update project README results table |
| `update_gallery` | `bazelisk run //scripts:update_gallery -- ...` | Update top-level README gallery table |
| `module_sizes` | `bazelisk run //scripts:module_sizes -- <synth_stat>` | Show hierarchical module cell counts |
| `copy_thumbnail` | `bazelisk run //scripts:copy_thumbnail -- ...` | Copy gallery screenshot to docs/ |
| `orfs_hash` | `bazelisk run //scripts:orfs_hash -- MODULE.bazel` | Extract ORFS version hash |
