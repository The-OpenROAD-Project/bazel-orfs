#!/usr/bin/env python3
import os
import sys
import subprocess


def main():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    subprocess.run([sys.executable] + sys.argv[1:], check=True, env=env)


if __name__ == "__main__":
    main()
