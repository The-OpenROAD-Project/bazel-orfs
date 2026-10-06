"""Create a .tar.gz from a manifest of src_path\tdst_path[\tkind] lines."""

import gzip
import os
import sys
import tarfile


def _normalize(info):
    """The same inputs give the same bytes: no owner, no timestamp. Bazel's
    outputs are read-only; a deployed tree is edited, so members are
    writable by the user."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode |= 0o200
    return info


def main():
    manifest_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(output_path, "wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0
    ) as gz, tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
        seen = set()
        with open(manifest_path) as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                src, dst = line.split("\t")[:2]
                if dst in seen:
                    continue
                seen.add(dst)
                # In the sandbox an input is an absolute link into the
                # execroot; storing that link would ship a path on the
                # builder. Store what it points at. A relative link is a
                # symlink artifact (a venv's interpreter) whose target
                # resolves inside the tree: keep it a link.
                if os.path.islink(src) and not os.path.isabs(os.readlink(src)):
                    tar.add(src, arcname=dst, filter=_normalize)
                else:
                    tar.add(os.path.realpath(src), arcname=dst, filter=_normalize)


if __name__ == "__main__":
    main()
