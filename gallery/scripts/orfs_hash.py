"""Extract the short ORFS git hash from MODULE.bazel.

Parses the image tag like "docker.io/openroad/orfs:26Q1-395-g5f96c41ce"
and outputs the short hash (e.g., "5f96c41").

Usage:
    orfs_hash.py [MODULE.bazel]
"""
import argparse
import re
import sys
from pathlib import Path


def extract_orfs_hash(module_bazel: str) -> str:
    """Extract short git hash from ORFS Docker image tag."""
    m = re.search(r'image\s*=\s*"[^"]*:.*-g([0-9a-f]+)"', module_bazel)
    if not m:
        return ""
    full_hash = m.group(1)
    return full_hash[:7]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_bazel", nargs="?", default="MODULE.bazel",
                        help="Path to MODULE.bazel (default: MODULE.bazel)")
    args = parser.parse_args()

    text = Path(args.module_bazel).read_text()
    h = extract_orfs_hash(text)
    if h:
        print(h)
    else:
        print("ERROR: Could not find ORFS image hash in MODULE.bazel", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
