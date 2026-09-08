"""Copy generated campaign results into the source tree.

Every table and figure in the write-up is generated from these files, so
they are checked in: a reader can re-derive the claims without paying for
the campaign, and a re-run shows up as a diff rather than as a silently
different number.

Run under `bazelisk run`, which sets BUILD_WORKSPACE_DIRECTORY; the
inputs arrive as runfiles. Refuses to run outside `bazelisk run`, because
resolving the destination against the current directory would scatter
results wherever the caller happened to be.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dest-dir",
        required=True,
        help="destination, relative to the workspace root",
    )
    ap.add_argument("files", nargs="+", help="runfiles paths to copy")
    args = ap.parse_args()

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        sys.exit(
            "BUILD_WORKSPACE_DIRECTORY is unset: run this through "
            "`bazelisk run`, not as a bare binary"
        )

    dest_dir = Path(workspace) / args.dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    for src in args.files:
        source = Path(src)
        if not source.exists():
            sys.exit("missing input %s" % src)
        # Strip the ".generated" marker the genrule outputs carry to keep
        # a bazel output name distinct from the checked-in file it feeds.
        name = source.name.replace(".generated.", ".")
        target = dest_dir / name
        shutil.copyfile(source, target)
        print("wrote %s" % target.relative_to(workspace))


if __name__ == "__main__":
    main()
