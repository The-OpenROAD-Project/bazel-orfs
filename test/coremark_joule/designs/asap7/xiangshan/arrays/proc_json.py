"""One module of the packed-vector elaboration after proc, and nothing
else, as yosys JSON: the input of entries.py.

    proc_json.py <yosys> <slang.so> <sv dir> <top> <out.json>
"""

import subprocess
import sys

from dryrun import closure


def main(argv):
    yosys, slang, sv_dir, top, out = argv[1:6]
    files = closure(sv_dir, top)
    script = "; ".join(
        [
            f"read_slang --top {top} " + " ".join(files),
            f"hierarchy -top {top}",
            "proc",
            f"write_json {out}",
        ]
    )
    r = subprocess.run(
        [yosys, "-q", "-m", slang, "-p", script], capture_output=True, text=True
    )
    if r.returncode:
        sys.exit(r.stdout[-3000:] + r.stderr[-3000:])


if __name__ == "__main__":
    main(sys.argv)
