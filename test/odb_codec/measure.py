"""What //tools/odb_codec does to the compressed size of a flow's .odb files.

Takes a TSV of `design<TAB>stock.odb<TAB>encoded.odb` rows: the same
stage output built with --//:odb_codec=false and with the codec on (see
measure.sh). For each pair:

- gate: decoding the encoded file gives the stock file, byte for byte. A
  flow with the codec on computed the same database as one without it.
- gate: openroad rewriting the stock file reproduces it, and says where
  its slots lie (the layout the flow's write_db handed the codec).
- gate: encoding the stock file with that layout gives the flow's
  encoded file, byte for byte.
- size: both files, raw and compressed with zstd at level 3, the level
  zstd defaults to; the codec compresses nothing, so the compressor and
  level are the same on both sides and only the byte order differs.
- time: encode and decode, the median of three.

Writes one CSV row per file and prints the markdown tables for the PR.
"""

import argparse
import csv
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

STAGES = [
    "1_synth",
    "2_floorplan",
    "3_place",
    "4_cts",
    "5_1_grt",
    "5_route",
    "6_final",
]

# Stands in for the codec while openroad rewrites a stock file: keeps the
# layout write_db hands it and leaves the file as written.
CAPTURE = """#!/bin/sh
case "$1" in
encode) cp "$3" "$ODB_CODEC_CAPTURE" ;;
decode) cat "$2" ;;
esac
"""

REWRITE = """read_db {src}
write_db {dst}
"""


def zstd_size(zstd, path):
    out = subprocess.run(
        [zstd, "-3", "-c", "-q", path], stdout=subprocess.PIPE, check=True
    ).stdout
    return len(out)


def timed(argv, **kwargs):
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        subprocess.run(argv, check=True, **kwargs)
        runs.append(time.perf_counter() - start)
    return statistics.median(runs)


def same(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def stage_of(path):
    return os.path.basename(path)[: -len(".odb")]


def encoded_magic(path):
    with open(path, "rb") as f:
        return f.read(8) == b"ODBCODEC"


def measure(row, tools, scratch):
    design, stock, encoded = row
    substep = stock == "-"
    if (not substep and encoded_magic(stock)) or not encoded_magic(encoded):
        sys.exit(
            "{}: {} must be a stock .odb and {} an encoded one; was the "
            "stock build overwritten?".format(design, stock, encoded)
        )
    work = tempfile.mkdtemp(dir=scratch)

    decode_s = timed([tools.codec, "decode", encoded], stdout=subprocess.DEVNULL)
    decoded = os.path.join(work, "decoded.odb")
    with open(decoded, "wb") as out:
        subprocess.run([tools.codec, "decode", encoded], stdout=out, check=True)
    if substep:
        # Kept only with the codec on, so there is no codec-off copy: the
        # decoded file is the original, and chain checked that when it
        # stored the delta.
        stock = decoded
    decoded_ok = "n/a" if substep else same(decoded, stock)

    capture = os.path.join(work, "capture.sh")
    with open(capture, "w") as f:
        f.write(CAPTURE)
    os.chmod(capture, 0o755)
    layout = os.path.join(work, "layout")
    rewritten = os.path.join(work, "rewritten.odb")
    script = os.path.join(work, "rewrite.tcl")
    with open(script, "w") as f:
        f.write(REWRITE.format(src=stock, dst=rewritten))
    env = dict(os.environ, ODB_CODEC=capture, ODB_CODEC_CAPTURE=layout)
    subprocess.run(
        [tools.openroad, "-no_init", "-no_splash", "-exit", script],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    rewrite_ok = same(rewritten, stock)

    encode_s = ""
    encode_ok = "n/a"
    if not substep:
        runs = []
        reencoded = os.path.join(work, "reencoded.odb")
        for _ in range(3):
            shutil.copyfile(stock, reencoded)
            start = time.perf_counter()
            subprocess.run([tools.codec, "encode", reencoded, layout], check=True)
            runs.append(time.perf_counter() - start)
        encode_s = round(statistics.median(runs), 4)
        encode_ok = same(reencoded, encoded)

    result = {
        "design": design,
        "stage": stage_of(encoded),
        "base": subprocess.run(
            [tools.codec, "base", encoded],
            stdout=subprocess.PIPE,
            check=True,
            text=True,
        ).stdout.strip(),
        "stock_bytes": os.path.getsize(stock),
        "encoded_bytes": os.path.getsize(encoded),
        "stock_zstd3": zstd_size(tools.zstd, stock),
        "encoded_zstd3": zstd_size(tools.zstd, encoded),
        "encode_s": encode_s,
        "decode_s": round(decode_s, 4),
        "decoded_is_stock": decoded_ok,
        "rewrite_is_stock": rewrite_ok,
        "encode_is_flow": encode_ok,
    }
    shutil.rmtree(work)
    return result


GATES = ("decoded_is_stock", "rewrite_is_stock", "encode_is_flow")


def passed(row):
    return all(row[g] in (True, "n/a") for g in GATES)


def ratio(stock, encoded):
    return "{:.2f}x".format(stock / encoded) if encoded else "-"


def tables(all_rows):
    rows = [r for r in all_rows if r["stage"] in STAGES]
    subs = [r for r in all_rows if r["stage"] not in STAGES]
    designs = []
    for r in rows:
        if r["design"] not in designs:
            designs.append(r["design"])
    stages = [s for s in STAGES if any(r["stage"] == s for r in rows)]

    def cell(design, stage):
        hits = [r for r in rows if r["design"] == design and r["stage"] == stage]
        if not hits:
            return "-"
        return ratio(
            sum(r["stock_zstd3"] for r in hits), sum(r["encoded_zstd3"] for r in hits)
        )

    out = []
    out.append(
        "Compressed size, stock over reformatted, zstd -3 on both "
        "(higher is better):\n"
    )
    out.append("| design | " + " | ".join(stages) + " |")
    out.append("|---|" + "---|" * len(stages))
    for d in designs:
        out.append("| {} | {} |".format(d, " | ".join(cell(d, s) for s in stages)))
    out.append("")
    out.append("Per design, every .odb of the flow together:\n")
    out.append(
        "| design | files | .odb raw | zstd -3 stock | zstd -3 reformatted "
        "| gain | encode | decode |"
    )
    out.append("|---|---|---|---|---|---|---|---|")
    for d in designs + ["all"]:
        hits = [r for r in rows if d == "all" or r["design"] == d]
        stock = sum(r["stock_zstd3"] for r in hits)
        enc = sum(r["encoded_zstd3"] for r in hits)
        out.append(
            "| {} | {} | {:.1f} MiB | {:.2f} MiB | {:.2f} MiB | {} | {:.2f} s "
            "| {:.2f} s |".format(
                "**all**" if d == "all" else d,
                len(hits),
                sum(r["stock_bytes"] for r in hits) / 2**20,
                stock / 2**20,
                enc / 2**20,
                ratio(stock, enc),
                sum(r["encode_s"] or 0 for r in hits),
                sum(r["decode_s"] for r in hits),
            )
        )
    if subs:
        out.append("")
        out.append(
            "Floorplan and place with every substep .odb kept, each stored as a "
            "delta against the next file of its stage; cost is the substeps' "
            "bytes as a share of the stage file's:\n"
        )
        out.append(
            "| design | stage | stage file | substeps stock | substeps kept "
            "| cost | stage + substeps |"
        )
        out.append("|---|---|---|---|---|---|---|")
        for d in designs:
            for stage, prefix in (("2_floorplan", "2_"), ("3_place", "3_")):
                key = [r for r in rows if r["design"] == d and r["stage"] == stage]
                sub = [
                    r
                    for r in subs
                    if r["design"] == d and r["stage"].startswith(prefix)
                ]
                if not key or not sub:
                    continue
                kf = key[0]
                stock = sum(r["stock_zstd3"] for r in sub)
                kept = sum(r["encoded_zstd3"] for r in sub)
                out.append(
                    "| {} | {} | {:.0f} KiB | {:.0f} KiB | {:.0f} KiB | {:.0f}% "
                    "| {} |".format(
                        d,
                        stage[2:],
                        kf["encoded_zstd3"] / 1024,
                        stock / 1024,
                        kept / 1024,
                        100 * kept / kf["encoded_zstd3"],
                        ratio(stock + kf["stock_zstd3"], kept + kf["encoded_zstd3"]),
                    )
                )
        stock = sum(r["stock_zstd3"] for r in all_rows)
        enc = sum(r["encoded_zstd3"] for r in all_rows)
        out.append("")
        out.append(
            "Every .odb, {} stage files and {} substeps: {:.2f} MiB -> {:.2f} MiB, "
            "{}.".format(
                len(rows), len(subs), stock / 2**20, enc / 2**20, ratio(stock, enc)
            )
        )
    failed = [g for g in GATES if not all(r[g] in (True, "n/a") for r in all_rows)]
    out.append("")
    out.append(
        "Gates, {} files: {}".format(
            len(all_rows),
            "all pass" if not failed else "FAILED: " + ", ".join(failed),
        )
    )
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--codec", required=True)
    parser.add_argument("--zstd", required=True)
    parser.add_argument("--openroad", required=True)
    parser.add_argument("pairs", help="TSV: design, stock .odb, encoded .odb")
    parser.add_argument("csv", help="where to write the per-file rows")
    args = parser.parse_args()

    tools = argparse.Namespace(
        codec=os.path.abspath(args.codec),
        zstd=os.path.abspath(args.zstd),
        openroad=os.path.abspath(args.openroad),
    )
    # openroad finds its Tcl library through its runfiles, which are ours.
    os.environ.setdefault("RUNFILES_DIR", os.path.abspath(".."))
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    os.chdir(workspace)

    with open(args.pairs) as f:
        pairs = [line.rstrip("\n").split("\t") for line in f if line.strip()]
    rows = []
    with tempfile.TemporaryDirectory(dir=os.path.join(workspace, "tmp")) as scratch:
        for pair in pairs:
            rows.append(measure(pair, tools, scratch))
            print(
                "{design} {stage}: {stock_zstd3} -> {encoded_zstd3}".format(**rows[-1]),
                file=sys.stderr,
            )
    with open(args.csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(tables(rows))
    return (
        0
        if all(
            r["decoded_is_stock"] and r["rewrite_is_stock"] and r["encode_is_flow"]
            for r in rows
        )
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
