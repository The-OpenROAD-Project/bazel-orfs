# Making `.odb` cheaper on the wire

**The question.** Can we, without increasing cognitive load for users or
maintainers, and without paying much compute cost, make `.odb` more
efficient *in compressed form* — on the wire and in the Bazel cache?

**Non-goal:** decompressed size on disk.

**The answer: yes, measured — a 45% reduction.** Reordering the bytes
of a `dbTable` block from record-major to field-major — the same bytes,
permuted, no recomputation and no semantics — takes the two tables that
are 62% of the compressed artifact from 75.8 MiB to 21.2 MiB: **121.6
MiB -> 67.0 MiB for a stage `.odb`**. The change is confined to
`dbTable`'s stream operators, needs no per-type code, moves no object
ids, and changes nothing a user or maintainer has to think about.

Two larger ideas were measured alongside it and are **not**
recommended: a cross-stage semantic delta, and a generative `.odb`
format that stops storing constructor output. Both would save more.
Neither pays for its cognitive load. They are recorded at the end so the
numbers survive.

---

## The baseline

Measured on a large design — 721,019 instances, 740,565 nets,
3,739,022 iterms, 8,097,253 power-grid boxes:

| artifact | raw | zstd -3 |
| --- | --- | --- |
| `3_1_place_gp_skip_io.odb` | 748,210,781 | 108,034,737 |
| `3_3_place_gp.odb` | 763,855,126 | 127,368,441 |

Bazel already compresses, so **~110-127 MB per stage is the baseline**,
not the raw size. `orfs_flow()` keeps six `.odb`s per design —
`2_floorplan`, `3_place`, `4_cts`, `5_1_grt`, `5_route`, `6_final`
(`STAGE_METADATA.result_names` in `private/stages.bzl`) — so a variant
costs ~0.7 GB of cache and wire, and a sweep multiplies that.

## Where the compressed bytes are

`-debug_odb io_size` puts 726.7 of 728.5 MiB inside
`dbDatabase/dbChip/dbBlock`. Tech and all libraries together are
1.8 MiB: **the PDK offers nothing to win and nothing to fear.**

Compressing the file in 16 MiB chunks and attributing the plateaus by
the `dbBlock` write order and the measured object counts:

| region | raw MiB | zstd MiB | ratio | share of compressed |
| --- | --- | --- | --- | --- |
| `iterm_tbl` — 3,739,022 iterms | 146.2 | 38.8 | 3.8x | 31.9% |
| `sbox_tbl` — 8,097,253 PDN boxes | 316.6 | 37.0 | 8.6x | 30.4% |
| `inst_tbl` — 721,019 instances | 97.2 | 23.6 | 4.1x | 19.4% |
| `box_tbl` + hierarchy tables | 60.0 | 16.3 | 3.7x | 13.4% |
| `net_tbl` — 740,565 nets | 79.4 | 5.9 | 13.4x | 4.9% |
| total | 728.5 | 121.6 | 6.0x | 100% |

Note what this corrects: the PDN is 43.6% of the *raw* file but only
30.4% of the compressed one, because a lattice of rectangles is what a
generic compressor is good at. Raw byte counts are the wrong
denominator throughout.

The `sbox_tbl` attribution is not inference. Scanning the file for a
fixed record stride — an allocated slot writes a `1` flag byte followed
by its payload — finds a **perfectly dense 41-byte slot array running
from ~416 MiB to EOF, alloc-flag hit rate 1.000**, which is exactly
8,097,253 x 41 B = 316.6 MiB. The other tables show no clean stride,
for a reason that turns out to matter (below).

## The change: field-major `dbTable` blocks

`dbTable` serialization (`src/odb/src/db/dbTable.inc:477-496`) walks
every slot of every page and writes each record's fields consecutively —
array-of-structs. So the file interleaves unrelated fields a few bytes
apart, which is the worst case for a compressor: the `net_` id of one
iterm sits between two fields of its neighbours, and no window size
helps.

Nothing in the byte stream says which bytes belong to the same field.
**Only the schema knows that**, which is why this is not something Bazel
or zstd could have picked up. Reorder each block of slots so that all
values of field 1 are adjacent, then all of field 2, and the columns
become near-constant or arithmetic ramps.

Measured on `sbox_tbl`, 48 MiB sample, zstd -3:

| transpose block | zstd bytes | vs as-written |
| --- | --- | --- |
| as written (array-of-structs) | 5,539,279 | 1.0x |
| 128 records — one `dbTable` page | 961,822 | 6x |
| 1,024 records | 341,836 | 16x |
| 8,192 records | 129,179 | **43x** |
| 65,536 records | 134,667 | 41x |
| whole table | 50,500 | 110x |

Robustness across the region — 24 MiB windows at 420, 470, 520, 570,
620 and 670 MiB — gives 90x to 180x, alloc-flag hit rate 1.000 in every
one. A seventh window at 715 MiB gives only 4x because it straddles the
end of the table and the transpose misaligns; that is the honest failure
mode, and the implementation knows where tables end.

Scaled to the whole 312 MiB PDN region: **35.3 MiB compressed -> ~1.0
MiB at whole-table granularity, ~5.9 MiB at page granularity.** Against
a 121.6 MiB artifact that is a 24-29% reduction from this one table.

Block size, not page size, is the knob. Bumping
`dbTable<_dbSBox>`'s page size would get the same effect and must not be
done: object id is `page_addr | slot`, so changing page size renumbers
ids. Transposing across a *stream block* spanning several pages keeps
the table structure and the ids exactly as they are.

### Why this costs nothing

* **Lossless by construction.** The same bytes in a different order. No
  regeneration, no derivation, no field dropped, nothing to verify
  beyond a round trip.
* **No ids move.** Slots keep their positions, so object ids,
  `next_box_` chains and `dbSet` iteration order are untouched. Nothing
  downstream can observe it — which is the whole point.
* **Near-zero compute, probably net faster.** An 8192 x 41 byte
  transpose per block is memory-bandwidth trivial, and there are ~34 MiB
  fewer bytes to compress and send.
* **Uncompressed size is unchanged** — which the stated non-goal makes
  free.
* **No per-type code.** Serialize each slot through the *existing*
  `operator<<` into a scratch buffer; if every allocated slot in the
  block produced the same payload length, write the alloc bitmap and the
  transposed matrix; otherwise write the block exactly as it is written
  today. Read reverses it and feeds the existing `operator>>`. One
  implementation in `dbTable.inc`, no `operator<<` variants to keep in
  sync, and nobody has to learn anything to add a field.

That last point is what keeps maintainer load at zero, and it is worth
stating as a hard design constraint: **if this needs a hand-written
field-major serializer per type, it is not worth doing.** The
buffer-and-transpose approach avoids that entirely.

### What it covers, and what it skips

The generic scheme applies to any table whose allocated records
serialize to a constant length. That includes the fixed-layout numeric
tables — `sbox_tbl` (40 B payload), `iterm_tbl` (40 B), `box_tbl`
(36 B), `guide_tbl` (35 B) — and excludes `inst_tbl` and `net_tbl`,
whose records carry an inline `char*` name and so vary in length. Those
two are 24.3% of the compressed file, and are also the two that already
compress reasonably, being name-dominated.

Free slots are not a problem, and are why only `sbox_tbl` scans as a
clean stride. A free slot serializes as 9 bytes — flag plus free-list
`next_`/`prev_` — against 41 for an allocated one, so any table the
resizer has punched holes in has no fixed stride at all. `sbox_tbl`
scans perfectly because `pdngen` creates its boxes in one pass and
nothing ever destroys one. The scheme handles holes by writing the alloc
bitmap first and transposing the allocated payloads and the free-slot
payloads as two separate matrices.

### `iterm_tbl` measured: 1.91x

`iterm_tbl` is the most expensive table after compression, so it decides
the total. It also has holes, which is what the alloc-bitmap handling is
for: a 64 MiB sample walks to 1,626,863 allocated slots and **45,264
free ones (2.7%)** — the resizer's fingerprint.

Locating it needed a structural scan rather than a header search,
because the `dbBlock` prologue contains variable-length strings so table
headers are not 4-byte aligned. Walking slot successors (41 bytes
allocated, 9 free) from every byte offset and keeping the starts that
survive 40 hops finds the table's data at file offset 4,294,027.
Alignment is confirmed semantically over 1.6M records: `ext_id_ == 0`
for 100%, `aps_` size `== 0` for 100%, `inst_` in range for 100%.

| layout | zstd bytes | vs as-written |
| --- | --- | --- |
| as written | 16,136,764 | 1.00x |
| field-major, 1,024-record blocks | 8,953,285 | 1.80x |
| field-major, 8,192-record blocks | 8,432,055 | **1.91x** |
| field-major, 65,536-record blocks | 8,065,988 | 2.00x |
| field-major, whole table | 7,942,803 | 2.03x |
| field-major + per-field int32 delta | 11,122,859 | 1.45x |

Two things to take from this. Field-major is worth ~1.9x here rather
than the PDN's 43x, because an iterm record is mostly object ids with no
lattice structure. And **per-field delta actively hurts** — it turns
permutation-like id columns into noise. Do not delta; just reorder.

Per-field cost, whole-table columns, zstd bytes:

| field | bytes | |
| --- | --- | --- |
| `prev_net_iterm_` | 3,693,946 | |
| `next_net_iterm_` | 3,503,348 | 66% of the column total, together |
| `net_` | 2,137,647 | the actual connectivity |
| `inst_` | 373,233 | near-monotone, so nearly free |
| `next_modnet_iterm_` | 335,788 | |
| `prev_modnet_iterm_` | 326,385 | |
| `flags_` | 273,412 | |
| `mnet_` | 200,483 | |
| `ext_id_` | 219 | all zero |
| `aps_` size | 219 | all zero |

**The doubly-linked list pointers are the single most expensive thing in
the file** — 7.2 MB of the 10.8 MB column total, more than three times
the connectivity they index.

### An optional second step, with a real cost

That table exposes one omission that is exactly recomputable with no
ordering choice at all: **`prev_net_iterm_` and `prev_modnet_iterm_`**.
The reverse pointer of a doubly-linked list is not a canonicalization —
given the head and the `next` chain, every `prev` follows by arithmetic.
It is a field-level omission, so records keep their slots and ids, and
nothing observable moves. It is worth 4.02 MB of the 10.8 MB column
total.

But it needs per-type code, which is the constraint stated above. That
makes it a separate decision rather than part of the same change, and it
should only be taken if the ~3% it adds is judged worth the first
type-specific serializer in the scheme. `next_` is *not* in this class:
it encodes the traversal order, and choosing one is the canonicalization
this document rejects.

### Total

At 8,192-record blocks — the realistic implementation point for both:

| table | zstd MiB now | after | measured |
| --- | --- | --- | --- |
| `sbox_tbl` | 37.0 | 0.86 | yes, 43x |
| `iterm_tbl` | 38.8 | 20.3 | yes, 1.91x |
| `box_tbl` + hierarchy | 16.3 | unmeasured | payload is 36 B, but the table is not where the size estimates predict |
| `inst_tbl`, `net_tbl` | 29.5 | 29.5 | variable-length, skipped by design |
| total | 121.6 | **67.0** | **45% reduction** |

**45% is measured**, covering the two tables that are 62% of the
compressed artifact. If `box_tbl` and the hierarchy tables behave like
`iterm_tbl`, the total goes to ~59 MiB and 51%. The optional `prev`
omission would add ~3%.

## Scope

1. Locate `box_tbl` and the hierarchy tables and measure them, the last
   unmeasured 13.4%. The structural slot-walk scan is the tool; the
   36-byte-payload walk did not survive anywhere in the window the size
   estimates predicted, so the layout arithmetic is off somewhere and
   worth resolving.
2. `NamedTable` wrappers for the remaining `dbBlock` tables so
   `-debug_odb io_size` reports per-table bytes directly instead of by
   chunk-plateau inference. Mechanical, ~40 lines, upstreamable on its
   own, useful to anyone sizing an `.odb`.
3. Buffer-and-transpose in `dbTable`'s stream operators behind a schema
   minor bump, with the same-length check and the as-written fallback.
4. Round-trip test: `read_db` -> `write_db` byte-identical, and ids and
   chains unchanged, on both a small design and a large one.

This has to go upstream to be sane. Kept local, bazel-orfs `.odb` files
stop being readable by stock OpenROAD, which breaks issue reproducers —
the thing these files are most needed for outside the cache. It is
upstreamable: `odb`'s reader is full of `isSchema(kSchemaFoo)` gates,
which is exactly how a format change like this lands, and every
OpenROAD user's cache gets smaller.

---

## Measured and rejected

Recorded so the numbers are not lost and the ground is not re-covered.

### Generic binary delta between stages — dead

The first differing byte between two adjacent place `.odb`s is at offset
1,964,470, and past it **92.7% of aligned 32-bit words differ**, only 5%
of them by less than 1024. Object tables are position-addressed, so one
inserted object shifts every later record and a copy-matcher has nothing
to copy. Consistent with bsdiff having been tried and failed.

### Cross-stage semantic delta — works, too expensive

Store what a stage *decided* — instance locations, IO pin placements,
route guides — and replay it onto the parent `.odb`. The physics is
excellent: the place hop's entire decision is 721,019 `(x, y)` pairs,
**5.8 MB raw, 0.8% of the file**, and roughly 64% of a stage `.odb` is
provably carried rather than decided.

Phase 0 was run and it passed: `read_db` -> `write_db` with no edits is
byte-identical on both a 464,899-byte and a 763,855,126-byte `.odb`,
same SHA-256 in and out. So OpenROAD's writer is a pure function of
in-memory state, and replay is not ruled out.

Rejected anyway, on cognitive load:

* **No mutate-only artifact boundary exists.** Only stage `.odb`s are
  kept, and all five hops bundle an object-creating operation — the
  place hop carries the resizer, cts carries repair_timing, grt carries
  the global-route grind. So every patch needs create/destroy replay,
  which has to reproduce free-list order and creation sequence. The
  cheap near-certain case never ships alone.
* A patch is **only decodable by the OpenROAD that packed it**, so a
  toolchain bump invalidates every stored patch.
* **The parent must be present**, so a cache hit becomes a recursive
  reconstruction, each hop a `read_db` plus a `write_db` — trading cache
  bytes for CPU on every hit, which is backwards.

### Generative format — works, too expensive

Stop storing what a constructor produces. `dbInst::create`
(`src/odb/src/db/dbInst.cpp:1383-1397`) turns `(master, name)` into one
instance, N iterms with `mterm_idx = i` and an `inst_` back-pointer, and
one bbox box initialized from the master. That subtree is **43% of the
compressed file and is the output of a function whose inputs are also in
the file**. Add the derived linked lists (`next_net_iterm_`,
`module_next_`, `next_entry_`, …), the hash tables, and a lattice
encoding of the PDN, and the estimate was 121.6 -> ~41 MiB, a 66%
reduction.

Rejected on the risk that made the distinction clear:

* **Omitting a *field* of a stored object costs nothing** — the record
  keeps its slot and id, and the decoder stamps the value back.
* **Omitting the *object* means the decoder must allocate it**, and ids
  then depend on allocation order. A design's real iterm ids were
  assigned interleaved with the resizer's destroys, so replaying creates
  from a clean table will not reproduce them. Renumbering changes table
  iteration order, and `dbSet` iteration order feeds tie-breaks in
  placement and routing — so the same design could place differently
  depending on whether it passed through a canonicalizing write. That is
  a reproducibility hazard, and expensive cognitive load however small
  the diff.

The field-major change above is the part of this idea that survives:
same target tables, none of the semantics, none of the risk.

### PDN dedup across stages — free, but small

`sbox_tbl` is bit-identical in all six stage `.odb`s of a design.
Sharing it across them saves ~30% of the compressed bytes of five of the
six files with no encoder at all. Superseded by the field-major change,
which gets the same bytes without any cross-file machinery, but worth
knowing.

## Method notes

Measurements came from the pinned toolchain via
`make run RUN_SCRIPT=...` on `//test/smoketest:lb_32x128_nangate45_place`
— a macro-free fast flow — reading a large `.odb` from an earlier run.
Object counts are from the pinned binary walking the database. Both
files carry schema `0.139`.

Two things worth knowing for anyone repeating this:

* `bazelisk run //:deps -- <stage target>` fails silently with exit 1
  for this target. `deps_wrapper.sh:38-40` greps `cquery --output=files`
  for a `.tar.gz` that this target's `_deps` outputs do not include, and
  under `set -o pipefail` the script dies before reaching its own error
  message. Use `bazel run <stage target> -- run RUN_SCRIPT=...` instead.
* `-debug_odb io_size` hides contributors under 1024 bytes and only
  names three tables inside `dbBlock`; the rest are streamed without a
  `NamedTable` wrapper. Hence scope item 2.
