#!/usr/bin/env python3
"""ORFS's aes RTL as one file, optionally with one sbox module per instance.

    aes_uniq.py [--copies] --out FILE aes_cipher_top.v aes_key_expand_128.v \
        aes_rcon.v aes_sbox.v

Without --copies the sources are concatenated, their `include of
timescale.v replaced by its one line at the top, and nothing else changed: the gold side of the
equivalence proof. With --copies each of the 20 aes_sbox instances (16 in
aes_cipher_top, us00..us33; 4 in aes_key_expand_128, u0..u3) gets a
module of its own, aes_sbox_<instance> for the cipher's and aes_sbox_k<n>
for the key expansion's, the body aes_sbox's: the same function, and a
hardened block per instance, so each gets its own pins. Anything that is
not that shape stops the script.

--break changes the first copy's first table entry (8'h00 -> 8'h63
becomes 8'h64): the negative control of the equivalence proof.
"""

import argparse
import re
import sys

SBOX = re.compile(r"^aes_sbox\s+(\w+)\s*\(", re.M)
INCLUDE = re.compile(r'^\s*`include\s+"timescale\.v"\s*$', re.M)


def read(paths):
    texts = {}
    for p in paths:
        name = p.rsplit("/", 1)[-1]
        with open(p) as f:
            texts[name] = INCLUDE.sub("", f.read())
    for need in (
        "aes_cipher_top.v",
        "aes_key_expand_128.v",
        "aes_rcon.v",
        "aes_sbox.v",
    ):
        if need not in texts:
            raise SystemExit("aes_uniq.py: %s not among the inputs" % need)
    return texts


def copies(texts):
    """Rename every aes_sbox instance's module; returns the extra modules."""
    extra = []
    for name, prefix, count in (
        ("aes_cipher_top.v", "", 16),
        ("aes_key_expand_128.v", "k", 4),
    ):
        insts = SBOX.findall(texts[name])
        if len(insts) != count:
            raise SystemExit(
                "aes_uniq.py: %s has %d aes_sbox instances, expected %d"
                % (name, len(insts), count)
            )
        for inst in insts:
            module = "aes_sbox_%s%s" % (prefix, inst if not prefix else inst[1:])
            texts[name] = re.sub(
                r"^aes_sbox(\s+%s\s*\()" % inst,
                module + r"\1",
                texts[name],
                count=1,
                flags=re.M,
            )
            body = texts["aes_sbox.v"]
            if body.count("module aes_sbox(") != 1:
                raise SystemExit(
                    "aes_uniq.py: aes_sbox.v does not declare module aes_sbox(a,d) once"
                )
            extra.append(body.replace("module aes_sbox(", "module %s(" % module))
    return extra


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--copies", action="store_true")
    ap.add_argument("--break", dest="broken", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("sources", nargs="+")
    a = ap.parse_args(argv)
    texts = read(a.sources)
    extra = copies(texts) if a.copies else []
    if a.broken:
        if not extra or "8'h00: d=8'h63;" not in extra[0]:
            raise SystemExit(
                "aes_uniq.py: --break needs --copies and an sbox table entry 8'h00: d=8'h63"
            )
        extra[0] = extra[0].replace("8'h00: d=8'h63;", "8'h00: d=8'h64;", 1)
    order = ["aes_cipher_top.v", "aes_key_expand_128.v", "aes_rcon.v", "aes_sbox.v"]
    with open(a.out, "w") as f:
        # timescale.v's one line, which every source included
        f.write("`timescale 1ns / 10ps\n")
        for name in order:
            f.write("// %s\n%s\n" % (name, texts[name]))
        for body in extra:
            f.write(body + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
