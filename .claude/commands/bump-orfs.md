> **Repo**: Run from the openroad-demo root.

Bump bazel-orfs and the ORFS Docker image to the latest version.

Run the following command:

```bash
bazelisk run @bazel-orfs//:bump
```

This updates both:
- The **bazel-orfs** git commit in MODULE.bazel (`git_override`)
- The **ORFS Docker image** tag and sha256 (`orfs.default`)

After bumping:

1. Check `git diff MODULE.bazel` to see what changed
2. Update the `bazel-orfs-verilog` `archive_override` commit to match the new bazel-orfs commit
3. Run `/demo-pr` to rebuild all projects and verify nothing regressed
4. If everything passes, commit the change

## OpenROAD versioning strategy

By default, all projects use OpenROAD from the **Docker image** — no from-source
builds. The bump command updates the Docker image to the latest release. This is
the recommended and simplest path.

If a specific project hits an OpenROAD bug, it can build a **patched OpenROAD
from source** and pass it via `openroad = "@openroad//:openroad"` in the
`orfs.default()` call. This is a project-specific workaround — the patched
OpenROAD should NOT be the default for all projects. Keep from-source builds
scoped to the project that needs them.

This is also useful for debugging — if a build issue might be a bazel-orfs bug,
bumping to the latest version may fix it.
