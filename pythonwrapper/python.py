#!/usr/bin/env python3
import runpy
import sys


def main():
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    runpy.run_path(script, run_name='__main__')


if __name__ == "__main__":
    main()
