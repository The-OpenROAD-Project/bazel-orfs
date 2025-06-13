#!/usr/bin/env python3
import sys
import subprocess


def main():
    subprocess.run([sys.executable] + sys.argv[1:], check=True)


if __name__ == "__main__":
    main()
