#!/usr/bin/env python3
"""Thin wrapper that downloads and runs the latest bump_impl.py from origin/main.
This ensures we always run the latest version with the newest bugfixes
and avoid the suckerpunch where an old bump.py corrupts MODULE.bazel before
it can be updated.
"""

import os
import sys
import urllib.request
import subprocess
import tempfile


def main():
    url = "https://raw.githubusercontent.com/The-OpenROAD-Project/bazel-orfs/main/bump_impl.py"

    # Allow overriding the implementation URL for testing
    if "BUMP_IMPL_URL" in os.environ:
        url = os.environ["BUMP_IMPL_URL"]

    print(f"Fetching latest bump implementation from {url}...")
    try:
        req = urllib.request.urlopen(url, timeout=15)
        script_content = req.read()
    except Exception as e:
        print(f"Failed to fetch latest bump implementation: {e}", file=sys.stderr)
        print(
            "Fallback: Attempting to run local bump_impl.py if available...",
            file=sys.stderr,
        )
        local_impl = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "bump_impl.py"
        )
        if os.path.exists(local_impl):
            sys.exit(
                subprocess.run([sys.executable, local_impl] + sys.argv[1:]).returncode
            )
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
        tf.write(script_content)
        temp_path = tf.name

    try:
        result = subprocess.run([sys.executable, temp_path] + sys.argv[1:])
        sys.exit(result.returncode)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    main()
