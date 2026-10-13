"""A register-file spec through ORFS's regfile_ram.py and generate_ram.

The netlist AUTO_MEMORIES_REGFILES inlines for the spec (the wrapper in
the RTL module's place around generate_ram's RAM), its module renamed
<module>_gen, for regfile_sim_test to simulate beside the reference
(--suffix "" keeps the name, for an equivalence check). With --shape
netlist or macro, --out is a directory that keeps every view.
"""

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--regfile-ram", required=True, type=Path)
    p.add_argument("--spec", required=True, type=Path)
    p.add_argument("--module", required=True)
    p.add_argument("--openroad", required=True)
    p.add_argument("--lef", action="append", default=[], type=Path)
    p.add_argument("--lib", action="append", default=[])
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--suffix", default="_gen")
    p.add_argument("--shape", default="inline", choices=["inline", "netlist", "macro"])
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location("regfile_ram", args.regfile_ram)
    regfile_ram = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regfile_ram)
    os.environ["LIB_FILES"] = " ".join(args.lib)
    if args.shape != "inline":
        args.out.mkdir(parents=True, exist_ok=True)
        regfile_ram.generate(
            args.spec, args.module, args.shape, args.openroad, args.lef, args.out
        )
        return 0
    with tempfile.TemporaryDirectory(dir=args.out.parent) as work:
        out_dir = Path(work) / "memories"
        out_dir.mkdir()
        regfile_ram.generate(
            args.spec, args.module, "inline", args.openroad, args.lef, out_dir
        )
        text = (out_dir / f"{args.module}.v").read_text()
    text = text.replace(
        f"module {args.module} (", f"module {args.module}{args.suffix} (", 1
    )
    args.out.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
