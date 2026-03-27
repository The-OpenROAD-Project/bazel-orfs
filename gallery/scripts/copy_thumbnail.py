"""Copy a gallery thumbnail to docs/<project>/.

Usage:
    copy_thumbnail.py <thumb_webp> <project>
"""
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("thumb_webp", help="Path to thumbnail .webp file")
    parser.add_argument("project", help="Project name (e.g., vlsiffra)")
    parser.add_argument("--docs-dir", default="docs", help="Docs directory (default: docs)")
    args = parser.parse_args()

    dest_dir = Path(args.docs_dir) / args.project
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "route.webp"
    shutil.copy2(args.thumb_webp, dest)
    print(dest)


if __name__ == "__main__":
    main()
