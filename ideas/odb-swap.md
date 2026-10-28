# A learned .odb reordering for Bazel's cache: 2x smaller, 50-100x too slow to encode

Status: **run, and answered: negative.** Stored stage `.odb` files get
about 2x smaller under Bazel's remote-cache `zstd -3`, with no change to
OpenROAD, but encoding runs at 2-4 MB/s on 16 cores. The bar was
hundreds of MB/s (XiangShan's stage files are gigabytes) together with
2x; the speed misses it by 50-100x, and by an estimated 2-5x even on
128 cores, because each large table is parsed on one core.

## Problem

A stage `.odb` is array-of-structs: fields of one kind are never next to
each other, so the cache's `zstd -3` cannot model them. Earlier attempts
that fixed this needed OpenROAD's help and are closed: the field-major
`dbTable` issue (OpenROAD #11328, 1.82x on one place file), the
structure-of-arrays switch (#11352, 1.38x, rejected) and the
`ODB_CODEC` hook with a schema-free codec (#11524, bazel-orfs #1081,
1.77x; the hook is dead upstream). The question here: can a tool outside
OpenROAD learn the layout from the bytes alone, and reorder them as fast
as the cache needs?

## Idea

`odb_swap`: a genome of grammars, one per table shape (header fields, a
counted repeat of slots, a tag byte choosing a record or a free slot,
fixed fields, length-prefixed strings, nested counted repeats, switches,
a check that a header count matches its slots). The encoder finds where
each grammar parses, sends every field to its own stream (byte planes,
causal predictors, a split of one field's values by another field's,
read ahead in the record; each stream divided by its gcd) and keeps the
rest as it is. Overlapping parses are chosen by the zstd bytes they save
(weighted interval scheduling). The genome travels in the file; decoding
needs no training and always reproduces the input byte for byte. A
genetic program evolves new regions (islands, restarts, sequential
covering, fitness = zstd bytes saved over the frozen genome); the study
seeded it with four tables transcribed from OpenROAD's `operator<<`.

Wired transparently into bazel-orfs behind a flag: the stage action
stores `X.odb.swapped`, an uncached decode action recreates `X.odb` at
its usual path, so every reader and every downstream cache key is
unchanged. gcd's floorplan and place stages built byte-identical to a
flag-off build and the repo's `.odb`, output-group and deploy tests
passed.

## Impact

Measured on 32 stage files (asap7 gcd, uart, riscv32i, aes every stage,
ibex synth to cts held out), `zstd -3` of stock over `zstd -3` of the
stored file:

| | all | synth-cts | grt | route | final |
|---|---|---|---|---|---|
| this genome (9 regions + gcd) | **1.98x** | 2.36-2.64x | 1.77x | 1.67x | 1.71x |
| #1081 (OpenROAD's layout) | 1.77x | 1.73-2.88x | 1.64-1.89x | 1.46-1.62x | 1.51-1.66x |

Held-out ibex 2.58x; riscv32i's routed files, never trained on, 1.87x.
What did not work, so it is not retried: byte shuffle, bitshuffle and
bytedelta at any element size or alignment (at best 1.00x, bitshuffle
0.56x); OpenZL v0.3.0 profiles, trained or not, without a format
description (1.08x); per-axis deltas on wire coordinates (worse, as
#1081 found). What did: splitting the wire data by its opcode (route
1.46x to 1.67x), choosing overlapping parses by value instead of
genome order or length.

The speed is the negative. A 22 MB route file encodes in 7.2 s on 16
threads (18.9 s on one) and decodes in 0.25 s; a 100 MB file encodes at
2-4 MB/s. 85-90% of encode is the anchor search: without OpenROAD saying
where tables start, the only way to find them is to try every grammar at
every byte, and `.odb` is full of the small integers and 0/1 bytes that
let near-misses parse a long way before failing. Grammar-derived
prefilters, chunked parallel scans and skipping past long claims bought
2x at most, and skipping lost compression whenever it trusted a region
without a check.

#1081 shows what the boundaries are worth. Its codec, handed OpenROAD's
`.layout` (where every table's slots lie), encoded its 42 stage files,
287 MB raw, in 3.49 s: 82 MB/s on one thread, 98 MB/s on the 23 MB
`aes/5_route`, decoding at 168-204 MB/s. It transposed known slots in
one pass; odb_swap's own walk of known regions runs at a similar ~90
MB/s. The 80x between them is the search for the layout. #11352, inside
OpenROAD's own write and read, left both times unchanged.

With wall time the only cost, more cores help, but not enough. On a
22 MB route file and 16 cores, encode went from 6.05 s to 1.91 s:

| configuration | wall | work | stored |
|---|---|---|---|
| 1 MB scan chunks, full genome | 6.05 s | 19.8 CPU-s | 2.60 MB |
| 64 KB chunks, every (chunk, region) its own job | 4.74 s | 34.3 CPU-s | 2.64 MB |
| same, without the two searched regions that have no check | 1.91 s | 15.9 CPU-s | 2.73 MB |
| hand-written, checked regions only | 1.55 s | 11.6 CPU-s | 2.95 MB |

The anchor scan splits into independent jobs and scales with cores; its
waste comes from regions with no check, whose near-miss parses run deep
before failing, so a search would have to require a check on every
region, for a few percent of compression. What does not scale: each
large table is walked start to finish on one core, three times (to
value it, to encode it, to verify the round trip), because records with
names or vectors have no fixed length to split on. That is about 0.6 s
per 22 MB, 35-45 MB/s, whatever the core count. Estimated, not
measured (no gigabyte `.odb` and no more than 16 cores here): a 1 GB
XiangShan file on 128 cores with the walks parallel per table and only
overlapping claims valued would take 10-15 s, 70-100 MB/s, nearer 150
MB/s with the three walks merged into one. Still short of hundreds; the
size of the largest table decides it, so measure that first.

## To rehydrate

Measure encode MB/s on a 100 MB single `.odb` first; the ratio is the
easy half.

What `.odb` looks like (OpenROAD `dbTable.inc`, `dbStream.h`): a table
is six u32 (`top_idx_` .. `free_list_`), then `page_cnt * page_size`
slots, each a byte (1 allocated, 0 free) then the record or a free
slot's two u32, then a u32 prop list. Strings are a u32 length
counting the NUL, the bytes and the NUL. Vectors are a u32 count then
the elements. `_dbWire` is flags, `dbVector<int> data_`,
`dbVector<u8> opcodes_` (same length, low 5 bits of an opcode say what
its data word is), net. Box flags mark an octagon in bit 5.

Design decisions that held:
- A grammar per region: fixed fields, length-prefixed strings, counted
  repeats (`field * k`, with a max), switches on an earlier field, and
  a check that a header count equals how often a field took a value.
- Each field to its own stream; byte planes; causal predictors
  (previous value per stream, enclosing repeat index, another field,
  inverse of a `next` chain); a split of a field by another field's
  value, also by one later in the record, read ahead by the encoder
  and taken from its stream by the decoder; each stream divided by its
  gcd. The genome travels in the file, so decoding needs no training.
- Overlapping parses chosen by the zstd -3 bytes each saves (weighted
  interval scheduling), not by genome order or length.
- Search: sequential covering seeded from the last genome, islands,
  restarts and immigrants against stalls; fitness the gain of the best
  selection with a candidate over the frozen genome alone.
- Bazel: the stage action stores `X.odb.swapped`; a `no-cache`,
  `no-remote` decode action writes `X.odb` at its usual path, so readers
  and downstream keys do not change.

Traps already hit: variable-length fields let a grammar parse the
wrong table (fix: NUL-terminated strings, repeat maxima, the count
check, failing as soon as a count passes its total); a dry parse must
step over plain fixed-size repeats or misaligned garbage counts walk
millions of elements; a region with no check can parse megabytes of
the wrong bytes, so it may never make others skip; chunked parallel
scans need stitching or a mid-table chunk start hides a real table;
valuing a claim must not copy the file before it.

## Effort

Large, and the verdict changes only with the table boundaries handed
over: OpenROAD's layout (the dead hook) or a parser for the `.odb`
structure (the per-table serializer #11328 ruled out). Either makes the
anchor search free, leaving a ~100 MB/s single-threaded transform as in
#1081, which spread across tables could plausibly reach hundreds of
MB/s. Not worth pursuing without one of those two.
