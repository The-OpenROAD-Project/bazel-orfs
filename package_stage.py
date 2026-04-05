"""Create a .tar.gz from a manifest of src_path\tdst_path lines."""

import os
import sys
import tarfile


def main():
    manifest_path = sys.argv[1]
    output_path = sys.argv[2]

    with tarfile.open(output_path, "w:gz") as tar:
        seen = set()
        with open(manifest_path) as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                src, dst = line.split("\t", 1)
                if dst in seen:
                    continue
                seen.add(dst)
                tar.add(src, arcname=dst)


if __name__ == "__main__":
    main()
