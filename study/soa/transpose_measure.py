#!/usr/bin/env python3
"""Measure what a field-major permutation of a dbTable's bytes compresses to.

Input is one table dumped by the study's `SoaDumpTable` tool: `<stem>.bin`
holds the per-slot records exactly as `dbTable::writePage` emits them, and
`<stem>.json` holds their lengths and the table's geometry.

The policy measured is the one the change can actually implement without
per-type code: take a block of N consecutive records, and **if every record
in the block came out the same length**, write the transposed matrix
(byte j of every record, for each j); otherwise write the block unchanged.
Same bytes either way -- a permutation -- so the only thing that moves is
what a compressor can find.

Block size is the knob, and it is not the table's page size: a table whose
pages hold 128 slots can still be written 8192 records at a time, and the
page size cannot be raised to match because an object id is
`page_addr | slot`.

Emits one CSV row per (table, codec, level, block size).
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

# Block sizes to sweep. 128 is sbox_tbl's page size -- the floor a
# page-local layout would be stuck with -- and 8192 is where the original
# measurement was taken.
BLOCK_SIZES = [128, 256, 512, 1024, 2048, 4096, 8192, 16384]


def compressed_size(data: bytes, codec: str, level: int) -> int:
    """Bytes after `codec` at `level`, measured by running the real codec."""
    if codec == "zstd":
        cmd = ["zstd", f"-{level}", "-c", "-T0", "--no-progress"]
    elif codec == "gzip":
        cmd = ["gzip", f"-{level}", "-c"]
    else:
        raise ValueError(f"unknown codec {codec}")
    out = subprocess.run(cmd, input=data, capture_output=True, check=True)
    return len(out.stdout)


def transpose_blocks(
    records: np.ndarray, lengths: np.ndarray, block: int, policy: str = "strict"
):
    """Field-major permutation of a block of records.

    Two policies, both schema-free -- neither needs to know what a field is,
    only that records of equal length line up:

    `strict`
        Transpose the block only if every record in it came out the same
        length; otherwise write the block exactly as today. Simplest possible
        reader, and the policy originally proposed.

    `classes`
        Partition the block by record length, transpose each length class,
        and pay for a per-slot class index so the reader can put them back.
        Costs ceil(log2(classes)) bits per slot, counted in the output here
        rather than assumed away.

    Returns the permuted stream, how many blocks were transposed whole, and
    the block count.
    """
    pieces = []
    homogeneous = 0
    blocks = 0
    offsets = np.concatenate(([0], np.cumsum(lengths)))

    for start in range(0, len(lengths), block):
        end = min(start + block, len(lengths))
        blocks += 1
        span = records[offsets[start] : offsets[end]]
        block_lengths = lengths[start:end]
        uniform = block_lengths.min() == block_lengths.max()

        if uniform:
            width = int(block_lengths[0])
            pieces.append(span.reshape(-1, width).T.tobytes())
            homogeneous += 1
        elif policy == "classes":
            classes = np.unique(block_lengths)
            # The class index the reader needs, packed to the bits it takes.
            bits = max(1, int(np.ceil(np.log2(len(classes)))))
            index = np.searchsorted(classes, block_lengths).astype(np.uint8)
            pieces.append(np.packbits(np.unpackbits(index)[:: 8 // bits]).tobytes())
            local = np.concatenate(([0], np.cumsum(block_lengths)))
            for width in classes:
                rows = [
                    span[local[i] : local[i + 1]]
                    for i in np.nonzero(block_lengths == width)[0]
                ]
                if rows:
                    matrix = np.stack(rows)
                    pieces.append(matrix.T.tobytes())
        else:
            pieces.append(span.tobytes())

    return b"".join(pieces), homogeneous, blocks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stems", nargs="+", help="dump stems, without .bin/.json")
    parser.add_argument("--csv", required=True, help="where to write the rows")
    parser.add_argument(
        "--policy",
        default="strict",
        choices=["strict", "classes"],
        help="what to do with a block whose records are not all one length",
    )
    parser.add_argument(
        "--codec",
        action="append",
        default=None,
        help="codec:level, repeatable (default zstd:3, zstd:19, gzip:6)",
    )
    args = parser.parse_args()

    codecs = args.codec or ["zstd:3", "zstd:19", "gzip:6"]
    codecs = [(c.split(":")[0], int(c.split(":")[1])) for c in codecs]

    rows = []
    for stem in args.stems:
        meta = json.loads(Path(stem + ".json").read_text())
        records = np.fromfile(stem + ".bin", dtype=np.uint8)
        lengths = np.array(meta["lengths"], dtype=np.int64)
        assert (
            lengths.sum() == records.size
        ), f"{stem}: lengths sum to {lengths.sum()} but .bin is {records.size}"

        table = meta["table"]
        raw = records.tobytes()
        for index, (codec, level) in enumerate(codecs):
            # The block sweep runs on the first codec only. The rest are
            # sanity checks that the effect is not a quirk of one
            # compressor, and cost far more per call (zstd -19 on a
            # few hundred MB is minutes), so they are measured at the
            # ends of the sweep only.
            blocks_to_measure = (
                BLOCK_SIZES if index == 0 else [BLOCK_SIZES[0], BLOCK_SIZES[-1]]
            )
            aos = compressed_size(raw, codec, level)
            for block in blocks_to_measure:
                permuted, homogeneous, blocks = transpose_blocks(
                    records, lengths, block, args.policy
                )
                soa = compressed_size(permuted, codec, level)
                rows.append(
                    {
                        "table": table,
                        "policy": args.policy,
                        "slots": meta["slots"],
                        "allocated": meta["allocated"],
                        "sizeof": meta["slot_bytes"],
                        "page_size": meta["page_size"],
                        "raw_bytes": len(raw),
                        "codec": codec,
                        "level": level,
                        "block": block,
                        "aos_bytes": aos,
                        "soa_bytes": soa,
                        "gain": round(aos / soa, 4) if soa else 0.0,
                        "homogeneous_blocks": homogeneous,
                        "blocks": blocks,
                    }
                )
                print(
                    f"{table:6s} {codec}:{level:<2d} block={block:<6d} "
                    f"aos={aos:>12,d} soa={soa:>12,d} "
                    f"gain={rows[-1]['gain']:>6.2f}x "
                    f"homogeneous={homogeneous}/{blocks}",
                    flush=True,
                )

    with open(args.csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.csv} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
