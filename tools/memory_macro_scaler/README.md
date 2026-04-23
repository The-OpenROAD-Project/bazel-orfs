# memory_macro_scaler

Predicts area, timing, and power for ASAP7 memory macros from a fitted
model, and emits `.lib` + `.lef` for consumption by `orfs_macro()`.
Two entry points:

- **`scale_macro()`** — rewrites an existing ORFS reference abstract's
  timing endpoints and pin positions to the fitted idiomatic values.
- **`behavioral_macros()`** — takes behavioral Verilog and emits one
  `orfs_macro()` per memory module, no synthesis or P&R.

The output is an `orfs_macro()` with both `OrfsInfo.lib` (post-CTS,
propagated clock) and `OrfsInfo.lib_pre_layout` (ideal clock) set, so
downstream flows consume it like any ORFS-characterized abstract.

## Where this sits in the flow

Pick RTL → DSE with the fitted model → converge on the memory shapes
the architecture wants → commit to a PDK memory compiler for those
shapes → tape out. The compiler step moves downstream instead of being
the entry point; DSE runs against a model with published residuals
instead of hand-picked numbers and a prayer.

## Classification from the `.lib` alone

Walks the Liberty cell's pins. First match wins:

1. `memory() { type : ram; address_width : N; word_width : W; }` → SRAM.
2. Firtool-convention pins `^(R|RW|W)\d+_(addr|data|en|mask|wmask|wdata|rdata|wmode|clk)$` → SRAM; port counts from distinct `(kind, num)` tuples, widths from `type()` blocks.
3. Name suffix `_<rows>x<bits>` plus a `ff(...)` group → flop memory.
4. Otherwise non-memory; `.lef` passes through, `.lib` timing-scales with a scalar.

## Fitted model

Per kind (`sram` or `ff`):

```
log(area_um2 / tech_nm²) = a + b · log(rows · bits · port_factor)
```

Two-parameter log-log regression in stdlib math; no numpy/scipy. The
`tech_nm²` factor is Dennard area scaling, which lets FreePDK45, sky130,
and ASAP7 points share one curve per kind.

- `port_factor`: 1RW=1.00, 1R1W=1.35, 2R1W=1.80 (OpenRAM paper).
- `access_time_ps ∝ tech_nm · log₂(rows) · √bits`, calibrated to OpenRAM FreePDK45 128×32×1RW = 322 ps.
- setup / hold / transition / CTS-insertion scale linearly with `tech_nm`
  from OpenRAM's FreePDK45 characterizer defaults.
- Flop memories: access_time = 0 (combinational read), CTS-insertion = 0.

### Data points

| Source | PDK | Kind | Rows × Bits × Ports | Area (μm²) | Access (ps) |
|---|---|---|---|---:|---:|
| OpenRAM (Cornell ECE5745) | FreePDK45 | SRAM | 128 × 32 × 1RW | 6,968 | 322 |
| DFFRAM | sky130A | FF | 128 × 32 × 1RW | 154,237 | — |
| DFFRAM | sky130A | FF | 256 × 32 × 1RW | 314,793 | — |
| DFFRAM | sky130A | FF | 512 × 32 × 1RW | 622,982 | — |
| DFFRAM | sky130A | FF | 1024 × 32 × 1RW | 1,249,648 | — |
| DFFRAM | sky130A | FF | 2048 × 32 × 1RW | 2,497,908 | — |
| OpenRAM | sky130A | SRAM | 256 × 32 × 1RW | 176,016 | — |
| OpenRAM | sky130A | SRAM | 512 × 32 × 1RW | 262,770 | — |
| OpenRAM | sky130A | SRAM | 1024 × 32 × 1RW | 436,822 | — |

References:

- Guthaus et al., *"OpenRAM: An Open-Source Memory Compiler,"* ICCAD 2016 — [PDF](https://escholarship.org/content/qt8x19c778/qt8x19c778_noSplash_b2b3fbbb57f1269f86d0de77865b0691.pdf)
- [Cornell ECE5745 Tutorial 8](https://cornell-ece5745.github.io/ece5745-tut8-sram/) — FreePDK45 anchor.
- [AUCOHL/DFFRAM](https://github.com/AUCOHL/DFFRAM) — sky130 FF-memory + OpenRAM area table.
- [VLSIDA/OpenRAM](https://github.com/VLSIDA/OpenRAM).
- [The-OpenROAD-Project/RegFileStudy](https://github.com/The-OpenROAD-Project/RegFileStudy) — port-sweep methodology.
- Muralimanohar et al., *"CACTI 5.1,"* HPL-2008-20 — access-time form.

### Residuals

Fit predicts each training point's value, compared to published:

| PDK | Rows × Bits | Kind | Published (μm²) | Predicted (μm²) | Error |
|---|---|---|---:|---:|---:|
| FreePDK45 | 128 × 32 | SRAM | 6,968 | 8,430 | +21% |
| sky130A | 128 × 32 | FF | 154,230 | 155,408 | +0.8% |
| sky130A | 256 × 32 | FF | 314,749 | 311,342 | −1.1% |
| sky130A | 512 × 32 | FF | 623,031 | 623,737 | +0.1% |
| sky130A | 1024 × 32 | FF | 1,249,649 | 1,249,584 | −0.0% |
| sky130A | 2048 × 32 | FF | 2,497,908 | 2,503,393 | +0.2% |
| sky130A | 256 × 32 | SRAM | 176,016 | 134,103 | −24% |
| sky130A | 512 × 32 | SRAM | 262,791 | 255,606 | −2.7% |
| sky130A | 1024 × 32 | SRAM | 436,824 | 487,196 | +12% |

FF ±1%, SRAM ±25%. FF-memory points share a PDK and port count so the
fit collapses cleanly; the SRAM residuals reflect pooling FreePDK45
(1 point) with sky130 (3 points) on one curve. A DSE decision whose
predicted delta is smaller than the residual band for that kind is
inside the noise.

A unit test (`test_training_residuals_inside_dse_budget`) pins the
budget.

## Banking (primer rule 3)

Oversized memories are silently decomposed inside the predictor; the
behavioral Verilog stays monolithic but the aggregated area / delay /
power are what a banked implementation would land at.

Per-bank limits:

| Limit | Value |
|---|---:|
| `MAX_ROWS_PER_BANK` | 512 |
| `MAX_BITS_PER_BANK` | 128 |
| `MAX_READ_PORTS_PER_BANK` | 2 |
| `MAX_WRITE_PORTS_PER_BANK` | 1 |

Composition order (from the memory modeling primer): word slice → row
bank → read-port replicate → write-port address-bank.

Aggregation:

- **Area** sums over all banks, wrapped in a 1:1..1:4 outline.
- **Access time** = single-bank access + `log₂(row_banks)` FO4 of mux
  select. Word-sliced banks fire in parallel; read copies serve
  independent ports.
- **Read/write energy per access** = per-bank × `word_slices`
  (word-sliced banks all fire; row-banked banks are clock-gated).
- **Leakage** sums over every bank.

`bucket["bank_plan"]` exposes the decomposition:

```
>>> role = mms.MemoryRole(kind="sram", rows=2048, bits=256, nR=2, nW=1)
>>> bucket, _ = mms.predict_idiomatic(role, tech_nm=7)
>>> bucket["bank_plan"]
BankPlan(rows/bank=512 bits/bank=128 slices=2 row_banks=4
         read_copies=2 write_addr_banks=1 total_banks=16)
```

## Behavioral-memory flow — no synthesis or P&R

For memories where the Verilog is a behavioral model, `behavioral_macros()`
emits a full `orfs_macro()` per module without running a flow. The only
EDA step is a Yosys read + elaborate to get the authoritative pin list
and flop structure — everything else (`.lib` body, `.lef`) comes from
the fitted model plus idiomatic pin placement.

Full ORFS abstract is minutes–hours per memory. The behavioral flow is
seconds per memory; negligible in incremental builds when the Verilog
is unchanged.

```
         behavioral .sv/.v
               │
               ▼
   ┌───────────────────────────┐
   │ Yosys: read + elaborate + │   ← only EDA step
   │ synth -run begin:proc     │
   └──────────────┬────────────┘
                  │  endpoint JSON
                  ▼
   ┌───────────────────────────┐      ┌───────────────────────────┐
   │ memory_macro_scaler       │◀─────│ fitted area/delay/power   │
   │ generate_lib()            │      │ (OpenRAM/DFFRAM trained)  │
   └──────────────┬────────────┘      └───────────────────────────┘
                  │
                  ▼
        synthesized .lib (timing + internal_power arcs)
                  │
                  └──► orfs_macro(lib, lef, module_top)
                              ▲
         pure-Python ─────────┘
         generate_lef()
```

### Power for OpenSTA SAIF flow

The generated `.lib` has:

- `default_cell_leakage_power` — static power, ~1 pW/bit @ 45 nm scaled.
- `internal_power()` on `clk` — per-edge average (read + write)/2, in fJ.
- `internal_power()` on each data/ctrl input pin — per-toggle energy.

Expected consumer flow:

```tcl
read_lib   mem_ram_128x64.lib
read_verilog  top.v
link_design   top
read_saif     top.saif -scope /top
report_power
```

Power is calibrated to OpenRAM FreePDK45 (~5 pJ/access at 128 × 32 × 1RW)
and scales with `tech_nm · rows · bits`. Residual band is similar to
area (±25%).

## Dual characterization

`orfs_macro()` carries two `.lib` files via `OrfsInfo`:
`lib` (propagated clock, post-CTS) and `lib_pre_layout` (ideal clock,
post-place). They differ only in `min/max_clock_tree_path` arcs.
`scaled_macro_lib.bzl` wraps the two scaled files into a single target
that forwards both through `OrfsInfo`; a bare file label as `lib =
...` drops `lib_pre_layout` silently.

## Usage

### `behavioral_macros()` — from Verilog

```starlark
load("@bazel-orfs//tools/memory_macro_scaler:behavioral_macros.bzl",
     "behavioral_macros")

behavioral_macros(
    name = "mem_macros",
    srcs = ["path/to/design.sv"],
    modules = ["ram_128x64", "regfile_32x32", ...],   # explicit list
    tech_nm = 7,
)
```

One `orfs_macro()` target per module; `target_suffix` available to
avoid collisions with existing demo_sram-style targets.

### `scale_macro()` — from a reference abstract

Dual-input (abstract_stage past place, bazel-orfs auto-emits the
pre-layout sibling):

```starlark
load("@bazel-orfs//tools/memory_macro_scaler:scale_macro.bzl", "scale_macro")

scale_macro(
    name = "mem_scaled",
    reference_lib_post_cts   = ":mem_lib",
    reference_lib_pre_layout = ":mem_lib_pre_layout",
    reference_lef            = ":mem_lef",
    module_top               = "mem",
)
```

Single-input (abstract_stage = place; scaler synthesizes both outputs
by rewriting clock-insertion arcs):

```starlark
scale_macro(
    name = "mem_scaled",
    reference_lib_post_cts = ":mem_lib",
    reference_lef          = ":mem_lef",
    module_top             = "mem",
)
```

### CLI

```sh
# Scale an existing reference dual characterization
bazel run @bazel-orfs//tools/memory_macro_scaler:memory_macro_scaler -- \
    --in-lib-post-cts A.lib [--in-lib-pre-layout B.lib] --in-lef C.lef \
    --out-lib-post-cts X.lib --out-lib-pre-layout Y.lib --out-lef Z.lef

# Generate abstracts from Verilog
bazel run @bazel-orfs//tools/memory_macro_scaler:memory_macro_scaler -- \
    --verilog path/ --out-dir DIR [--module NAME ...] [--tech-nm N]
```

`--dry-run` skips writes.

## ASAP7 characterization sweep

`characterization/asap7_sweep.yaml` is a committed YAML of characterized
ASAP7 shapes; the fit auto-loads its points at startup. Shapes are
listed in `characterization/sweep_configs.py` and span four regimes
(depth sweep at 32 b, width sweep at 128 rows, port sweep at 64 × 32,
bit-line sweep at 64 b, masked-write sweep).

Regenerate:

```sh
bazel run //tools/memory_macro_scaler/characterization:pin_asap7_sweep
```

Uses `BUILD_WORKSPACE_DIRECTORY` to write back into the source tree.
With no per-shape result files wired yet, writes a schema-documented
empty stub. The per-shape `orfs_flow()` targets are declared by the
consumer (ascenium, gallery, etc.) — this tool only harvests.

## Testing

```sh
bazel test //tools/memory_macro_scaler/...
```

~40 Python unit tests (inline fixtures, no filesystem) plus Bazel-level
integration tests (`lib_pre_layout_test` on the scaled macro, file
accumulation, dual-char content diff, place-only variants).

## Pointers

- `orfs_macro()` + `OrfsInfo.lib_pre_layout`: `bazel-orfs/private/rules.bzl`.
- Pre-layout abstract emission: `bazel-orfs/private/flow.bzl` around `_emit_pre_layout_abstract()`.
- Memory modeling primer: `ascenium plan/33-memory-modeling-primer.md` (on the `memory-modeling-primer` branch).
- Sweep schema: `characterization/asap7_sweep.yaml`.
