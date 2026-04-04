"""Create a portable tarball from a stage manifest.

Reads a manifest file (one "src_path\\tdst_path" per line) and creates
a tar.gz archive with the mapped files.  All files are stored as real
copies — no symlinks — so the archive works outside the Bazel cache.

Lines starting with "INLINE:" contain inline content:
  INLINE:<content>\\t<dst_path>
"""

import io
import os
import sys
import tarfile
import time


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <manifest> <output.tar.gz>", file=sys.stderr)
        sys.exit(1)

    manifest_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(manifest_path) as f:
        entries = [
            line.rstrip("\n").split("\t", 1)
            for line in f
            if line.strip() and "\t" in line
        ]

    now = time.time()

    with tarfile.open(output_path, "w:gz") as tar:
        for src, dst in entries:
            if src.startswith("INLINE:"):
                content = src[len("INLINE:") :].encode()
                info = tarfile.TarInfo(name=dst)
                info.size = len(content)
                info.mode = 0o755
                info.mtime = now
                tar.addfile(info, io.BytesIO(content))
                continue

            if not os.path.exists(src):
                print(f"warning: {src} not found, skipping", file=sys.stderr)
                continue

            # Resolve symlinks so the archive contains real files.
            real_src = os.path.realpath(src)
            info = tar.gettarinfo(real_src, arcname=dst)
            # Make all files user-writable so extracted archives are editable.
            info.mode |= 0o200
            info.mtime = now
            if info.isreg():
                with open(real_src, "rb") as fobj:
                    tar.addfile(info, fobj)
            else:
                tar.addfile(info)


if __name__ == "__main__":
    main()
