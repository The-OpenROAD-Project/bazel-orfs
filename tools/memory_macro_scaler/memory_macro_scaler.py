"""Scale a reference dual characterization (.lib pre-layout + .lib post-CTS + .lef)
to an idiomatic ASAP7 PDK memory macro.

Separation of concerns
----------------------
The *upstream RTL* (e.g. ascenium/hardware/aptos) is responsible for picking
memory shapes that match the memory modeling primer: D*W > 1024 bits becomes
PDK SRAM with <= 2R/1W and registered output; D*W <= 1024 bits with many
ports stays as flops with combinational reads; and so on. This tool assumes
that decision has already been made. It does not judge whether a shape is
idiomatic.

Given a reference `.lib`+`.lib`(pre_layout)+`.lef` produced by ORFS
characterization of such a memory, this tool emits a scaled dual
characterization: timing endpoints land where an idiomatic ASAP7 SRAM
compiler of the same shape *would* land, and the `.lef` outline + pin
positions follow ASAP7 memory-macro conventions (addr/ctrl on the left,
data-out on the right, clock on top, aspect ratio 1:1..1:4).

Why dual characterization?
--------------------------
`orfs_macro()` in bazel-orfs carries two Liberty files through its OrfsInfo
provider: `lib_pre_layout` (ideal-clock, used by parent synth/floorplan/place)
and `lib` (propagated-clock, used from parent CTS on). They differ in the
`min/max_clock_tree_path` arcs — the macro's internal clock-insertion latency.
Both must be scaled, kept in lockstep, and re-exposed as an OrfsInfo-providing
target (`scaled_macro_lib` in scale_macro.bzl) or downstream synth silently
drops back to ideal-clock accuracy. See bazel-orfs/private/rules.bzl.

Classification
--------------
The tool decides SRAM vs flop-memory vs non-memory from the `.lib` alone, by
walking the cell's pin list. Layers, first-hit wins:

  1. `memory() { type : ram; address_width; word_width }` group -> SRAM.
  2. Firtool pin-name convention `^(R|RW|W)\\d+_(addr|data|...)$` -> SRAM.
  3. Library/cell name suffix `_<rows>x<bits>` plus a `ff(...)` group in
     a cell -> flop_memory.
  4. None of the above -> non_memory (just timing-scale through, no LEF
     rewrite, no idiomatic-table lookup).

For SRAM we derive (rows, bits, nR, nW, nRW). For flop_memory we derive
(rows, bits) from the name suffix.

Idiomatic ASAP7 table
---------------------
A Python dict indexed by (rows, bits, ports_key) holds reference values for
an idiomatic ASAP7 SRAM of that shape. Adding a new entry is a deliberate
act: each bucket is a claim about what the PDK compiler would actually emit.
Aspect ratios are asserted to sit in [1, 4] at build time (enforced in the
unit tests).
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Idiomatic memory area/delay model — fitted from published data
# ---------------------------------------------------------------------------
# Instead of a hand-entered bucket table, the tool fits a two-parameter model
# per memory kind (sram / ff) over concrete area numbers pulled from
# published OpenRAM and DFFRAM characterizations on multiple PDKs.
# The fit is technology-node agnostic: area is scaled by the square of the
# technology node (classic Dennard-ish area scaling) so sky130 + FreePDK45
# points collapse onto one curve per kind, and we can predict ASAP7 (7 nm)
# by plugging tech_nm = 7 into the fitted expression.
#
# Model: log(area_um2 / tech_nm^2) = a + b * log(rows * bits * port_factor(ports))
#
#   predicted_area_um2 = exp(a) * tech_nm^2 *
#                        (rows * bits * port_factor(ports)) ** b
#
# Port overhead comes from multi-port bit-cell area scaling as described
# in the OpenRAM paper (Guthaus et al., ICCAD 2016): each extra read port
# adds ~30% to bit-cell area; a write port is ~50%. Approximate factors
# are applied as a multiplicative area scalar.
#
# Access time is a single scalar technology-linear term calibrated to the
# one SRAM access-time data point with a known number
# (OpenRAM/FreePDK45 128x32 1RW → 322 ps read delay, Cornell ECE5745). The
# fit is deliberately conservative; for the decoder depth contribution we
# use log2(rows), and for the bit-line length contribution sqrt(bits).
#
# Setup/hold come from OpenRAM's FreePDK45 defaults for the characterizer's
# DFF (approximately 50 ps setup and 20 ps hold at 45 nm; see
# VLSIDA/OpenRAM compiler/characterizer/setup_hold.py). Scaled linearly
# with tech_nm.
#
# Data sources
# ------------
#   [1] Cornell ECE5745 Tutorial 8 "SRAM Generators" — OpenRAM-generated
#       SRAM_32x128_1rw.lib at FreePDK45: area 6967.66 um^2, read delay
#       0.322 ns. https://cornell-ece5745.github.io/ece5745-tut8-sram/
#   [2] AUCOHL/DFFRAM README area comparison table (sky130A), with columns
#       for both the DFFRAM FF-compiler and OpenRAM SRAM at matching sizes.
#       https://github.com/AUCOHL/DFFRAM
#   [3] M. R. Guthaus et al., "OpenRAM: An Open-Source Memory Compiler,"
#       ICCAD 2016. Methodology and multi-port bit-cell overhead.
#   [4] The-OpenROAD-Project/RegFileStudy — register-file port-count study
#       confirming that flops absorb extra ports without PPA cliff (used
#       as a sanity check on the port_factor for the "ff" kind).
#       https://github.com/The-OpenROAD-Project/RegFileStudy

import math


# --- Published data points ---------------------------------------------------
# Each tuple: (tech_nm, rows, bits, ports_key, kind, area_um2, access_ps_or_None)
# tech_nm:   technology node in nanometers.
# kind:      "sram" or "ff".
# area_um2:  published macro outline area in um^2.
# access_ps: read access time in picoseconds, or None if not published.
#
# Keep this list small — every entry is a claim that a specific (pdk, shape)
# macro was really characterized with that number. New entries should cite
# their source in a trailing comment.
MEMORY_DATA_POINTS = [
    # [1] OpenRAM FreePDK45 — Cornell ECE5745 tutorial SRAM_32x128_1rw.
    (45,  128,  32, "1RW", "sram",  6967.66, 322.0),
    # [2] DFFRAM sky130A — byte-write 32-bit-word register RAM, 1RW.
    (130,  128, 32, "1RW", "ff",   396.52 * 388.96, None),   # 512 B
    (130,  256, 32, "1RW", "ff",   792.58 * 397.12, None),   # 1 KB
    (130,  512, 32, "1RW", "ff",   792.58 * 786.08, None),   # 2 KB
    (130, 1024, 32, "1RW", "ff",  1584.24 * 788.80, None),   # 4 KB
    (130, 2048, 32, "1RW", "ff",  1589.00 * 1572.00, None),  # 8 KB
    # [2] OpenRAM sky130A — from the same DFFRAM README table.
    (130,  256, 32, "1RW", "sram",  386.00 * 456.00, None),  # 1 KB
    (130,  512, 32, "1RW", "sram",  659.98 * 398.18, None),  # 2 KB
    (130, 1024, 32, "1RW", "sram",  670.86 * 651.14, None),  # 4 KB
]


# --- Banking (primer rule 3 decomposition) ---------------------------------
# Oversized behavioral memories are decomposed into banks so each bank
# stays within an idiomatic compiler sweet spot. The decomposition is
# applied to the prediction — not to the behavioral Verilog, which stays
# monolithic. Downstream consumers see one macro abstract whose area /
# delay / power numbers reflect a banked implementation.
#
# Limits per bank (rough ASAP7-scale compiler sweet-spot; adjustable):
#   rows <= 512      # decoder depth cost rises sharply above this
#   bits <= 128      # bit-line RC dominates above this
#   nR   <= 2        # PDK SRAM bit-cell limit (primer rule 2)
#   nW   <= 1        # PDK SRAM bit-cell limit (primer rule 2)
#
# Transforms applied in primer order: word slice -> row bank -> read-port
# replicate. Write-port banking is not automated (it requires an
# address-disjointness guarantee from upstream logic); when nW > 1 we
# assume the upstream code knows what it's doing and model it as a
# straight multi-bank with separate write addrs per bank.
MAX_ROWS_PER_BANK = 512
MAX_BITS_PER_BANK = 128
MAX_READ_PORTS_PER_BANK = 2
MAX_WRITE_PORTS_PER_BANK = 1


class BankPlan:
    """Decomposition plan for one logical memory.

    Fields:
      rows_per_bank / bits_per_bank : dimensions of each physical bank
      nR_per_bank   / nW_per_bank   / nRW_per_bank : ports on each bank
      word_slices   : number of word-sliced copies (all fire in parallel
                      on every access; outputs concatenated)
      row_banks     : number of row-banks (only one fires per access;
                      mux on the read path)
      read_copies   : number of read-port-replicated copies
                      (per-copy serves MAX_READ_PORTS_PER_BANK reads)
      write_addr_banks : number of address-banked writers
                         (nW split; only 1 fires per access)
      num_banks     : total macro count = slices * row_banks * read_copies
                                           * write_addr_banks
    """
    __slots__ = ("rows_per_bank", "bits_per_bank",
                 "nR_per_bank", "nW_per_bank", "nRW_per_bank",
                 "word_slices", "row_banks", "read_copies",
                 "write_addr_banks", "num_banks")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k, 0))
        self.num_banks = (
            self.word_slices * self.row_banks
            * max(self.read_copies, 1) * max(self.write_addr_banks, 1)
        )

    def __repr__(self):
        return (f"BankPlan(rows/bank={self.rows_per_bank} "
                f"bits/bank={self.bits_per_bank} "
                f"slices={self.word_slices} row_banks={self.row_banks} "
                f"read_copies={self.read_copies} "
                f"write_addr_banks={self.write_addr_banks} "
                f"total_banks={self.num_banks})")


def _ceil_div(a, b):
    return -(-a // b)


def bank_plan(role):
    """Decompose a logical memory into an idiomatic set of banks.

    See primer rule 3 in plan/33-memory-modeling-primer.md for the
    composition order. For flop-backed memories we still compute a
    plan (same limits apply — flop arrays above ~1024 bits hit routing
    congestion) but caller may choose to ignore it.
    """
    rows = max(role.rows, 1)
    bits = max(role.bits, 1)
    # Normalize ports into an RW-inclusive (read, write) tally for decomp.
    # 1RW counts as 1 read-port and 1 write-port for the limits, but all
    # on one physical port. We encode this as nRW_per_bank at the end.
    total_reads = role.nR + role.nRW
    total_writes = role.nW + role.nRW

    # 1. Word slice: split bits across parallel copies.
    word_slices = _ceil_div(bits, MAX_BITS_PER_BANK)
    bits_per = _ceil_div(bits, word_slices)

    # 2. Row bank: split rows across address-selected copies.
    row_banks = _ceil_div(rows, MAX_ROWS_PER_BANK)
    rows_per = _ceil_div(rows, row_banks)

    # 3. Read-port replicate (only if we need more than the per-bank limit).
    read_copies = max(_ceil_div(total_reads, MAX_READ_PORTS_PER_BANK), 1)

    # 4. Write-port address-bank (requires upstream disjointness guarantee;
    # modeled but not automatically enforced).
    write_addr_banks = max(_ceil_div(total_writes, MAX_WRITE_PORTS_PER_BANK), 1)

    # Per-bank port topology after decomposition: each bank has either
    # 1RW (preserve the RW nature), or up to 2R/1W.
    if role.nRW and not role.nR and not role.nW:
        nRW_per = 1
        nR_per = 0
        nW_per = 0
    else:
        nR_per = min(total_reads, MAX_READ_PORTS_PER_BANK)
        nW_per = min(total_writes, MAX_WRITE_PORTS_PER_BANK)
        nRW_per = 0

    return BankPlan(
        rows_per_bank=rows_per,
        bits_per_bank=bits_per,
        nR_per_bank=nR_per,
        nW_per_bank=nW_per,
        nRW_per_bank=nRW_per,
        word_slices=word_slices,
        row_banks=row_banks,
        read_copies=read_copies,
        write_addr_banks=write_addr_banks,
    )


def _per_bank_ports_key(plan):
    """The ports_key for one bank of a decomposition."""
    if plan.nRW_per_bank == 1:
        return "1RW"
    if plan.nR_per_bank == 2 and plan.nW_per_bank == 1:
        return "2R1W"
    if plan.nR_per_bank == 1 and plan.nW_per_bank == 1:
        return "1R1W"
    return "1RW"


# Port overhead: multi-port bit-cells are bigger. Values track OpenRAM's
# 10T isolated-read cell (~2.4x the 6T cell for 1RW+1R) spread across
# practical macro-level overheads — our "idiomatic" is a well-optimized
# macro that pushes periphery down so the per-port area cost is closer
# to the bit-cell ratio than the full 2.4x.
PORT_AREA_FACTOR = {
    "1RW":  1.00,
    "1R1W": 1.35,   # 1 read + 1 write: added read-only word-line
    "2R1W": 1.80,   # 2 read + 1 write: two read-only word-lines
}

# Access-path delay overhead vs 1RW (small; multi-port adds mux select only).
PORT_DELAY_FACTOR = {
    "1RW":  1.00,
    "1R1W": 1.05,
    "2R1W": 1.10,
}


# --- Fit ---------------------------------------------------------------------
# Pure-stdlib two-parameter linear regression in log space:
#   log(area / tech_nm^2) = a + b * log(rows * bits * port_factor)
# Fit per kind independently. We do not depend on numpy/scipy.

def _linear_regression(xs, ys):
    """Return (a, b) minimizing sum((a + b*x_i - y_i)^2). Needs >= 2 points."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return my, 0.0
    b = num / den
    a = my - b * mx
    return a, b


def _fit_area_model(data_points):
    """Return {kind: (a, b)} from MEMORY_DATA_POINTS."""
    out = {}
    for kind in {"sram", "ff"}:
        xs, ys = [], []
        for tech, rows, bits, ports_key, dp_kind, area, _ in data_points:
            if dp_kind != kind:
                continue
            x = math.log(rows * bits * PORT_AREA_FACTOR[ports_key])
            y = math.log(area) - 2 * math.log(tech)  # area-per-tech^2
            xs.append(x)
            ys.append(y)
        if len(xs) >= 2:
            out[kind] = _linear_regression(xs, ys)
        elif len(xs) == 1:
            # Single point: slope = 1 (area ~ linear in bit-count), intercept
            # fixed to the observation. Good enough as a fallback.
            out[kind] = (ys[0] - xs[0], 1.0)
        else:
            out[kind] = (0.0, 1.0)
    return out


def _load_sweep_yaml(path):
    """Append rows from a committed sweep-results YAML to MEMORY_DATA_POINTS.

    File format is documented in characterization/asap7_sweep.yaml.
    Missing or empty files are silently skipped — the sweep runs
    manual, and pre-sweep the YAML is a shell.
    """
    try:
        import yaml
    except ImportError:
        return []
    try:
        raw = path.read_text()
    except OSError:
        return []
    try:
        doc = yaml.safe_load(raw) or {}
    except Exception:
        return []
    runs = doc.get("runs") or []
    out = []
    for r in runs:
        try:
            out.append((
                int(r["tech_nm"]),
                int(r["rows"]),
                int(r["bits"]),
                str(r["ports_key"]),
                str(r["kind"]),
                float(r["area_um2"]),
                float(r["access_time_ps"])
                    if r.get("access_time_ps") is not None else None,
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


# Load committed sweep results (if any) and mix them into the fit.
_SWEEP_YAML = (
    Path(__file__).parent / "characterization" / "asap7_sweep.yaml"
)
MEMORY_DATA_POINTS = MEMORY_DATA_POINTS + _load_sweep_yaml(_SWEEP_YAML)
_AREA_FIT = _fit_area_model(MEMORY_DATA_POINTS)


def predict_area_um2(*, rows, bits, ports_key, kind, tech_nm):
    """Predicted macro outline area at the given shape + technology node."""
    a, b = _AREA_FIT[kind]
    pf = PORT_AREA_FACTOR.get(ports_key, 1.0)
    return math.exp(a) * (tech_nm ** 2) * ((rows * bits * pf) ** b)


def predict_access_time_ps(*, rows, bits, ports_key, kind, tech_nm):
    """Predicted read-access delay.

    Calibrated to OpenRAM FreePDK45 128x32 1RW = 322 ps ([1]).
    Decoder depth term log2(rows), bit-line load sqrt(bits).
    Flop-based memories have combinational reads (primer rule 1) → 0 ps.
    """
    if kind == "ff":
        return 0.0
    # Calibration: at tech=45, rows=128, bits=32, 1RW → 322 ps.
    shape = math.log2(max(rows, 2)) * math.sqrt(max(bits, 1))
    k = 322.0 / (45.0 * (math.log2(128) * math.sqrt(32)))
    return k * tech_nm * shape * PORT_DELAY_FACTOR.get(ports_key, 1.0)


def predict_setup_ps(tech_nm):
    """OpenRAM FreePDK45 characterizer DFF setup ~50 ps at 45 nm, linear scale."""
    return 50.0 * (tech_nm / 45.0)


def predict_hold_ps(tech_nm):
    """OpenRAM FreePDK45 characterizer DFF hold ~20 ps at 45 nm, linear scale."""
    return 20.0 * (tech_nm / 45.0)


def predict_transition_ps(tech_nm):
    """Output-slew target, roughly FO4 ratio. FreePDK45 FO4 ~20 ps."""
    return 20.0 * (tech_nm / 45.0)


def predict_clk_period_min_ps(*, rows, bits, ports_key, kind, tech_nm):
    """Min clock period = access + setup + margin."""
    return (
        predict_access_time_ps(rows=rows, bits=bits, ports_key=ports_key,
                               kind=kind, tech_nm=tech_nm)
        + 2 * predict_setup_ps(tech_nm)
    )


def predict_read_energy_fj(*, rows, bits, ports_key, kind, tech_nm):
    """Predicted dynamic energy per read access, in femtojoules.

    Model (from CACTI's access-path energy decomposition):
        E_read ≈ (C_wordline + C_bitline) · V_dd² / 2
    With C_bitline ∝ rows (one cell drives one bit-line per column) and
    C_wordline ∝ bits (one row driver drives all columns), and
    capacitance per unit length ∝ tech_nm.

    Calibrated to an OpenRAM-typical 5 pJ per read at 45 nm for the
    128 × 32 × 1RW shape (Guthaus et al., ICCAD 2016). Flop-based
    memories dissipate only the read-mux capacitance — ≈ 10% of an
    SRAM read of equivalent shape.
    """
    # Calibration anchor: 45 nm, 128 rows, 32 bits, 1RW → ~5000 fJ for SRAM.
    k = 5000.0 / (45.0 * 128.0 * 32.0)
    base = k * tech_nm * rows * bits * PORT_DELAY_FACTOR.get(ports_key, 1.0)
    if kind == "ff":
        return 0.1 * base
    return base


def predict_write_energy_fj(*, rows, bits, ports_key, kind, tech_nm):
    """Write energy — typically ~2× read in SRAMs (write drivers drain both
    bit-lines full-swing; read only drops them a few hundred mV).

    For flop-backed memories, write energy is the clock-distribution +
    flop-flip energy; scales linearly with bits (one flop per bit in
    the addressed row) and ~constant in rows.
    """
    if kind == "ff":
        k = 100.0 / (45.0 * 32.0)  # ~100 fJ at 45nm, 32-bit word → scales with tech_nm, bits
        return k * tech_nm * bits
    return 2.0 * predict_read_energy_fj(
        rows=rows, bits=bits, ports_key=ports_key, kind=kind, tech_nm=tech_nm)


def predict_leakage_pw(*, rows, bits, ports_key, kind, tech_nm):
    """Total static leakage, in picowatts.

    Model: per-bit leakage scales roughly inversely with tech_nm in
    modern nodes (smaller transistors, but FinFETs' lower leakage
    compensates) — use a constant per-bit leakage as a first-order
    DSE anchor. OpenRAM reports leakage at the library header as
    `default_cell_leakage_power`; typical FreePDK45 6T SRAM ≈ 1 pW/bit.
    """
    # Calibration: 1 pW/bit for an SRAM cell at 45 nm, scaled linearly
    # with tech_nm (aggressive-but-honest for 7 nm FinFET).
    per_bit_pw = 1.0 * (tech_nm / 45.0)
    if kind == "ff":
        # Flops leak about 3× an SRAM bit-cell (4 transistors vs 6,
        # but FFs have more internal nodes and drive strength).
        per_bit_pw *= 3.0
    return per_bit_pw * rows * bits * PORT_AREA_FACTOR.get(ports_key, 1.0)


def predict_post_cts_ck_insertion_ps(tech_nm, kind):
    """Typical on-macro clock-tree insertion latency.

    SRAM macros run a small internal CTS during their own physical design;
    observed latencies scale roughly linearly with the technology node.
    At 45 nm, ~500 ps is a typical mid-size SRAM figure; we use a
    proportional scale. Flop-based memories have no internal CTS —
    the parent clock tree drives each flop directly.
    """
    if kind == "ff":
        return 0.0
    return 500.0 * (tech_nm / 45.0)


def _predict_outline(area_um2, rows, bits):
    """Aspect-ratio-respecting outline picking (width, height) for area.

    Aim for aspect in [1:1, 1:4] (primer rule 4). Start with sqrt(area)
    and then squash/stretch toward the rows/bits ratio (taller memories
    get taller outlines).
    """
    import math as _m
    if area_um2 <= 0:
        return 1.0, 1.0
    # Desired width/height ratio: clamp log-ratio to keep aspect in [1, 4].
    raw = rows / max(bits, 1)
    ratio = max(0.5, min(raw, 2.0))   # caps composite aspect at 4:1
    height = _m.sqrt(area_um2 * ratio)
    width = area_um2 / height
    return width, height


# --- Idiomatic lookup: the public contract the rest of the tool talks to ----

# ASAP7 predictive PDK is 7 nm. Override if you're characterising a different
# node with scale_reference(..., tech_nm=...).
DEFAULT_TECH_NM = 7


def predict_idiomatic(role, tech_nm=DEFAULT_TECH_NM):
    """Return (bucket_dict, warning_or_none) for a classified memory role.

    Aggregates per-bank predictions across the rule-3 decomposition
    (see BankPlan). Access time takes the single-bank delay plus a
    bank-select mux penalty (log2(row_banks) FO4 gates). Read energy
    sums over word-sliced banks (they all fire); row-banked siblings
    don't fire on an access so they don't contribute. Leakage sums
    over every bank. Area is sum over all banks, wrapped in a single
    idiomatic-aspect outline.
    """
    if role.kind == "non_memory":
        return None, None

    kind = "ff" if role.kind == "flop_memory" else "sram"
    plan = bank_plan(role)
    per_bank_ports = _per_bank_ports_key(plan)
    rows_pb = plan.rows_per_bank
    bits_pb = plan.bits_per_bank

    # Access-time penalty for the bank-select mux on the read path. Each
    # level of banking adds roughly one FO4 gate (~tech_nm * 4 ps) of
    # select delay; with row_banks banks we traverse log2(row_banks) mux
    # levels.  Read-copy replication is free (no shared mux — each copy
    # serves its own read port).
    access_per_bank = predict_access_time_ps(
        rows=rows_pb, bits=bits_pb, ports_key=per_bank_ports,
        kind=kind, tech_nm=tech_nm)
    bank_mux_ps = 0.0
    if plan.row_banks > 1:
        bank_mux_ps = math.log2(plan.row_banks) * tech_nm * 4.0
    access_ps = access_per_bank + bank_mux_ps

    # Read energy: word-sliced banks all fire; row-banked banks do not.
    # Read-copies do fire for independent reads, but for a single access
    # only one fires — so on a per-access basis read energy multiplies
    # by word_slices, not num_banks.
    read_fj_per_bank = predict_read_energy_fj(
        rows=rows_pb, bits=bits_pb, ports_key=per_bank_ports,
        kind=kind, tech_nm=tech_nm)
    read_fj = read_fj_per_bank * plan.word_slices

    # Write energy: same pattern — word_slices banks fire per write.
    write_fj_per_bank = predict_write_energy_fj(
        rows=rows_pb, bits=bits_pb, ports_key=per_bank_ports,
        kind=kind, tech_nm=tech_nm)
    write_fj = write_fj_per_bank * plan.word_slices

    # Leakage: sum over every bank (all powered, whether firing or not).
    leakage_per_bank = predict_leakage_pw(
        rows=rows_pb, bits=bits_pb, ports_key=per_bank_ports,
        kind=kind, tech_nm=tech_nm)
    leakage_pw = leakage_per_bank * plan.num_banks

    bucket = dict(
        clk_period_min_ps=access_ps + 2 * predict_setup_ps(tech_nm),
        access_time_ps=access_ps,
        setup_ps=predict_setup_ps(tech_nm),
        hold_ps=predict_hold_ps(tech_nm),
        transition_ps=predict_transition_ps(tech_nm),
        pre_layout_ck_insertion_ps=0.0,
        post_cts_ck_insertion_ps=predict_post_cts_ck_insertion_ps(tech_nm, kind),
        read_energy_fj=read_fj,
        write_energy_fj=write_fj,
        leakage_pw=leakage_pw,
        bank_plan=plan,
    )
    if kind == "sram":
        area_per_bank = predict_area_um2(
            rows=rows_pb, bits=bits_pb, ports_key=per_bank_ports,
            kind=kind, tech_nm=tech_nm)
        total_area = area_per_bank * plan.num_banks
        w, h = _predict_outline(total_area, role.rows, role.bits)
        bucket["width_um"] = w
        bucket["height_um"] = h
        bucket["area_um2"] = total_area
    warning = None
    if per_bank_ports not in PORT_AREA_FACTOR:
        warning = f"unknown per-bank ports_key '{per_bank_ports}'; assuming 1RW"
    return bucket, warning


def lookup_idiomatic(role, tech_nm=DEFAULT_TECH_NM):
    """Thin wrapper around predict_idiomatic() preserved for the old API."""
    return predict_idiomatic(role, tech_nm=tech_nm)


# ---------------------------------------------------------------------------
# .lib classification
# ---------------------------------------------------------------------------

_LIBRARY_NAME_RE = re.compile(r"^\s*library\s*\(\s*([^\s)]+)\s*\)", re.MULTILINE)
_CELL_NAME_RE = re.compile(r"^\s*cell\s*\(\s*([^\s)]+)\s*\)", re.MULTILINE)
_MEMORY_SUFFIX_RE = re.compile(r"_(\d+)x(\d+)(?:_\d+)?$")
_MEMORY_GROUP_RE = re.compile(
    r"\bmemory\s*\(\s*\)\s*\{[^}]*?type\s*:\s*ram\b[^}]*?"
    r"address_width\s*:\s*(\d+)[^}]*?word_width\s*:\s*(\d+)",
    re.DOTALL,
)

# Firtool pin-name pattern.  Captures: (kind, port_num, tail).
# tail in {addr, en, mask, wmask, data, rdata, wdata, wmode, clk}.
_FIRTOOL_PIN_RE = re.compile(
    r"^(R|RW|W)(\d+)_(addr|en|mask|wmask|data|rdata|wdata|wmode|clk)$"
)

# Liberty pin/bus declarations: `pin(NAME)` or `bus(NAME)`. Works for both
# compact single-line and multi-line Liberty.
_PIN_OR_BUS_RE = re.compile(r"\b(?:pin|bus)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")

# bus_type NAME_DATA -> bit_width N.  We match `type (<name>) { ... bit_width : N; }`.
_TYPE_BLOCK_RE = re.compile(
    r"\btype\s*\(\s*([^\s)]+)\s*\)\s*\{[^}]*?\bbit_width\s*:\s*(\d+)",
    re.DOTALL,
)

# ff(IQ,IQN) group marker inside cell(...) — tells us it's a flop cell.
_FF_GROUP_RE = re.compile(r"\bff\s*\(\s*\w+\s*,\s*\w+\s*\)")


@dataclass
class MemoryRole:
    kind: str  # "sram" | "flop_memory" | "non_memory"
    rows: int = 0
    bits: int = 0
    nR: int = 0
    nW: int = 0
    nRW: int = 0
    library_name: str = ""
    cell_name: str = ""
    port_pin_names: dict = field(default_factory=dict)

    @property
    def ports_key(self):
        if self.kind != "sram":
            return None
        if self.nRW and not (self.nR or self.nW):
            return f"{self.nRW}RW"
        return f"{self.nR}R{self.nW}W"


def classify(lib_text):
    """Classify the first (and, here, only) cell in a Liberty file.

    Returns a MemoryRole. Never raises on non-memory input — falls through to
    kind="non_memory".
    """
    lib_m = _LIBRARY_NAME_RE.search(lib_text)
    cell_m = _CELL_NAME_RE.search(lib_text)
    library_name = lib_m.group(1) if lib_m else ""
    cell_name = cell_m.group(1) if cell_m else library_name
    role = MemoryRole(
        kind="non_memory",
        library_name=library_name,
        cell_name=cell_name,
    )

    # Layer 1: memory() group declares ram directly.
    mem_m = _MEMORY_GROUP_RE.search(lib_text)
    if mem_m:
        addr_bits = int(mem_m.group(1))
        role.kind = "sram"
        role.rows = 2 ** addr_bits
        role.bits = int(mem_m.group(2))
        _count_ports_firtool(role, lib_text)
        if role.nR == 0 and role.nW == 0 and role.nRW == 0:
            # memory() group said "ram" but no firtool pins — assume 1RW.
            role.nRW = 1
        return role

    # Layer 2: firtool-style pin names.
    pins = _PIN_OR_BUS_RE.findall(lib_text)
    firtool_hits = [_FIRTOOL_PIN_RE.match(p) for p in pins]
    firtool_hits = [m for m in firtool_hits if m]
    if firtool_hits:
        role.kind = "sram"
        _count_ports_firtool(role, lib_text)
        role.rows, role.bits = _infer_dims_from_pin_widths(lib_text, firtool_hits)
        if role.rows == 0 or role.bits == 0:
            # Fall back to library/cell name suffix if pins didn't pin
            # the dimensions (e.g. tests that omit type() blocks).
            dims = _dims_from_name(cell_name or library_name)
            if dims:
                role.rows, role.bits = dims
        return role

    # Layer 3: name suffix + ff() group => flop_memory.
    dims = _dims_from_name(cell_name or library_name)
    if dims and _FF_GROUP_RE.search(lib_text):
        role.kind = "flop_memory"
        role.rows, role.bits = dims
        return role

    # Layer 4: fall through as non_memory.
    return role


def _dims_from_name(name):
    m = _MEMORY_SUFFIX_RE.search(name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _count_ports_firtool(role, lib_text):
    """Populate nR/nW/nRW from firtool-style pin names in the lib."""
    seen = {"R": set(), "W": set(), "RW": set()}
    port_pin_names = {}
    for name in _PIN_OR_BUS_RE.findall(lib_text):
        m = _FIRTOOL_PIN_RE.match(name)
        if not m:
            continue
        kind, num, _tail = m.group(1), m.group(2), m.group(3)
        seen[kind].add(num)
        port_pin_names.setdefault(kind + num, []).append(name)
    role.nR = len(seen["R"])
    role.nW = len(seen["W"])
    role.nRW = len(seen["RW"])
    role.port_pin_names = port_pin_names


def _infer_dims_from_pin_widths(lib_text, firtool_hits):
    """Return (rows, bits) from type() blocks referenced by the pin set.

    rows derived from the widest addr bus (2 ** addr_width); bits from the
    widest data bus.  Returns (0, 0) if the .lib omits type() blocks.
    """
    types = {name: int(width) for name, width in _TYPE_BLOCK_RE.findall(lib_text)}

    # Find each bus's bus_type using a simple regex; not a full LEF/lib parser.
    bus_types = dict(re.findall(
        r"\bbus\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\{[^}]*?bus_type\s*:\s*([A-Za-z_][A-Za-z0-9_]*)",
        lib_text,
        flags=re.DOTALL,
    ))

    addr_bits = 0
    data_bits = 0
    for m in firtool_hits:
        base_name = f"{m.group(1)}{m.group(2)}_{m.group(3)}"
        tail = m.group(3)
        bus_type = bus_types.get(base_name)
        width = types.get(bus_type, 0) if bus_type else 0
        if tail == "addr":
            addr_bits = max(addr_bits, width)
        elif tail in ("data", "rdata", "wdata"):
            data_bits = max(data_bits, width)
    rows = (2 ** addr_bits) if addr_bits else 0
    return rows, data_bits


# ---------------------------------------------------------------------------
# .lib scaling (dual-characterization aware)
# ---------------------------------------------------------------------------
# Lifted from ascenium/hardware/tile/scale_lib.py — a line-by-line walker
# tracking brace depth and the open timing()/internal_power() group.
# Extended here to accept per-timing-type scale factors so we can hit the
# idiomatic numbers without squashing the rise/fall ratio or slew/load LUT
# shape of the input.

_CLOCK_TREE_TYPES = frozenset({"min_clock_tree_path", "max_clock_tree_path"})
_TIMING_OPEN = "__timing__"
_POWER_OPEN = "__power__"


def _scale_values_line(line, factor):
    def repl(m):
        val = float(m.group(2)) * factor
        return m.group(1) + f"{val:.6g}" + m.group(3)
    return re.sub(
        r'(values\s*\(\s*")(-?[\d.]+(?:[eE][+-]?\d+)?)("\s*\))',
        repl,
        line,
    )


def scale_lib_text(
    text,
    *,
    timing_scale=1.0,
    ck_insertion_ps=None,
    power_scale=1.0,
):
    """Return a scaled copy of a Liberty file's text.

    timing_scale   multiplier applied to data-path cell_rise/fall, setup/hold,
                   and output transition.
    ck_insertion_ps absolute target (picoseconds) for min/max_clock_tree_path
                   arcs.  If not None, *overrides* the existing values with
                   this number (preserves rise/fall ordering by writing the
                   same value to both).  If None, leaves clock-tree arcs
                   unchanged.
    power_scale    multiplier for internal_power tables.
    """
    out = []
    brace_depth = 0
    stack = []  # (tag, enter_depth)

    # time_unit lets us convert ck_insertion_ps -> library unit value.
    time_unit_factor = _parse_time_unit(text)  # e.g. 1e-9 for "1ns"
    ck_target = (ck_insertion_ps * 1e-12 / time_unit_factor) if ck_insertion_ps is not None else None

    for line in text.splitlines(keepends=True):
        opens = line.count("{")
        closes = line.count("}")
        if re.search(r"\btiming\s*\(\s*\)\s*\{", line):
            stack.append((_TIMING_OPEN, brace_depth + opens))
        elif re.search(r"\binternal_power\s*\(\s*\)\s*\{", line):
            stack.append((_POWER_OPEN, brace_depth + opens))

        m = re.search(r"\btiming_type\s*:\s*(\w+)", line)
        if m:
            for idx in range(len(stack) - 1, -1, -1):
                if stack[idx][0] == _TIMING_OPEN:
                    stack[idx] = (m.group(1), stack[idx][1])
                    break

        scale = None
        absolute_value = None
        for tag, _ in reversed(stack):
            if tag == _POWER_OPEN:
                scale = power_scale
                break
            if tag == _TIMING_OPEN:
                break
            if tag in _CLOCK_TREE_TYPES:
                if ck_target is not None:
                    absolute_value = ck_target
                    break
                scale = timing_scale
                break
            scale = timing_scale
            break

        if absolute_value is not None:
            line = re.sub(
                r'(values\s*\(\s*")(-?[\d.]+(?:[eE][+-]?\d+)?)("\s*\))',
                lambda m: m.group(1) + f"{absolute_value:.6g}" + m.group(3),
                line,
            )
        elif scale is not None:
            line = _scale_values_line(line, scale)

        out.append(line)
        brace_depth += opens - closes
        stack = [(tag, d) for tag, d in stack if d <= brace_depth]

    return "".join(out)


def _parse_time_unit(text):
    m = re.search(r'\btime_unit\s*:\s*"\s*(\d+(?:\.\d+)?)\s*(ps|ns|us)\s*"', text)
    if not m:
        return 1e-9  # Liberty default
    val, unit = float(m.group(1)), m.group(2)
    return val * {"ps": 1e-12, "ns": 1e-9, "us": 1e-6}[unit]


def compute_timing_scale(role, bucket, reference_text):
    """Pick a data-path timing scale so the reference lands near the idiomatic number.

    Strategy: find the largest `values ("X")` inside a setup/hold/combinational
    arc in the reference, compare against the idiomatic access_time, and
    return the ratio. This preserves the LUT shape while hitting the target.
    If the reference has no cell_rise values to key off, return 1.0.
    """
    if bucket is None:
        return 1.0
    target = bucket.get("access_time_ps", bucket.get("setup_ps", 0.0)) * 1e-12
    time_unit = _parse_time_unit(reference_text)
    vals = [
        float(m.group(1))
        for m in re.finditer(r'values\s*\(\s*"(-?[\d.]+(?:[eE][+-]?\d+)?)"\s*\)', reference_text)
    ]
    if not vals or target == 0.0:
        return 1.0
    # Use the max data-path value as the "characteristic" delay.
    characteristic = max(vals) * time_unit
    if characteristic == 0.0:
        return 1.0
    return target / characteristic


# ---------------------------------------------------------------------------
# .lef rewrite
# ---------------------------------------------------------------------------
# We do not parse the full LEF grammar. We preserve the preamble, rewrite the
# MACRO outline, re-emit pins in idiomatic positions, and write one OBS
# rectangle covering the interior.

_M4_PITCH_UM = 0.048  # ASAP7 M4 track pitch
_M5_PITCH_UM = 0.068  # ASAP7 M5 track pitch


def _is_output_pin(name):
    return bool(re.match(r"^R\d+_(data|rdata)$|^RW\d+_rdata$", name))


def _is_clock_pin(name):
    return name.lower() in ("clk", "clock") or re.match(r"^R\d+_clk$|^W\d+_clk$|^RW\d+_clk$", name)


def _is_power_pin(name):
    return name.upper() in ("VDD", "VSS", "VDDPE", "VSSE", "VDDCE")


def _is_input_pin(name):
    if _is_output_pin(name) or _is_clock_pin(name) or _is_power_pin(name):
        return False
    return True  # everything else goes on the input (left) edge


def rewrite_lef(lef_text, role, bucket):
    """Rewrite the LEF so outline and pins land on idiomatic ASAP7 positions.

    Returns the new LEF text. For non-SRAM roles, returns lef_text unchanged.
    """
    if role.kind != "sram" or bucket is None:
        return lef_text

    # Preserve the preamble (everything up to the first MACRO line).
    macro_m = re.search(r"^MACRO\s+(\S+)\s*$", lef_text, re.MULTILINE)
    if not macro_m:
        return lef_text
    preamble = lef_text[:macro_m.start()]
    macro_name = macro_m.group(1)
    pins = _PIN_OR_BUS_RE.findall(lef_text) or []
    # Extract all PIN names from LEF (distinct from .lib pins).
    pin_names = [m.group(1) for m in re.finditer(
        r"^\s*PIN\s+(\S+)\s*$", lef_text, re.MULTILINE
    )]

    width = bucket["width_um"]
    height = bucket["height_um"]
    aspect = max(width, height) / min(width, height)
    if not (1.0 - 1e-9 <= aspect <= 4.0 + 1e-9):
        raise ValueError(
            f"idiomatic bucket for {role.cell_name} has aspect {aspect:.2f}, "
            f"outside 1:1..1:4 window"
        )

    inputs = sorted([p for p in pin_names if _is_input_pin(p)])
    outputs = sorted([p for p in pin_names if _is_output_pin(p)])
    clocks = sorted([p for p in pin_names if _is_clock_pin(p)])
    powers = sorted([p for p in pin_names if _is_power_pin(p)])

    def _bank(edge_count, edge_length):
        if edge_count == 0:
            return []
        step = edge_length / (edge_count + 1)
        return [step * (i + 1) for i in range(edge_count)]

    lines = [preamble.rstrip("\n") + "\n" if preamble else ""]
    lines.append(f"MACRO {macro_name}\n")
    lines.append("  CLASS BLOCK ;\n")
    lines.append("  ORIGIN 0 0 ;\n")
    lines.append(f"  SIZE {width:.3f} BY {height:.3f} ;\n")

    # Inputs on the left edge (x=0), on M4.
    for name, y in zip(inputs, _bank(len(inputs), height)):
        _emit_pin(lines, name, "INPUT", layer="M4",
                  x=0.0, y=y, w=_M4_PITCH_UM, h=_M4_PITCH_UM)
    # Outputs on the right edge (x=width), on M4.
    for name, y in zip(outputs, _bank(len(outputs), height)):
        _emit_pin(lines, name, "OUTPUT", layer="M4",
                  x=width - _M4_PITCH_UM, y=y, w=_M4_PITCH_UM, h=_M4_PITCH_UM)
    # Clocks on the top edge (y=height), on M5.
    for name, x in zip(clocks, _bank(len(clocks), width)):
        _emit_pin(lines, name, "INPUT", layer="M5",
                  x=x, y=height - _M5_PITCH_UM, w=_M5_PITCH_UM, h=_M5_PITCH_UM,
                  use="CLOCK")
    # Power pins preserved at well-known positions (top-left / top-right).
    for i, name in enumerate(powers):
        _emit_pin(lines, name, "INOUT", layer="M5",
                  x=(width * 0.25) + (width * 0.5 * i),
                  y=height - _M5_PITCH_UM,
                  w=_M5_PITCH_UM, h=_M5_PITCH_UM,
                  use="POWER" if name.upper().startswith("VDD") else "GROUND")

    # One OBS rectangle covering the interior (conservative blockage).
    inset = _M4_PITCH_UM
    lines.append("  OBS\n")
    lines.append(f"    LAYER M4 ; RECT {inset:.3f} {inset:.3f} "
                 f"{width - inset:.3f} {height - inset:.3f} ;\n")
    lines.append("  END\n")
    lines.append(f"END {macro_name}\n")
    return "".join(lines)


def _emit_pin(lines, name, direction, *, layer, x, y, w, h, use=None):
    lines.append(f"  PIN {name}\n")
    lines.append(f"    DIRECTION {direction} ;\n")
    if use:
        lines.append(f"    USE {use} ;\n")
    lines.append("    PORT\n")
    lines.append(f"      LAYER {layer} ; RECT {x:.3f} {y:.3f} {x+w:.3f} {y+h:.3f} ;\n")
    lines.append("    END\n")
    lines.append(f"  END {name}\n")


# ---------------------------------------------------------------------------
# From-scratch .lib / .lef generation (no reference abstract required)
# ---------------------------------------------------------------------------
# Given only a memory role + target tech_nm, synthesize a complete Liberty
# file (with timing arcs and internal_power groups that OpenSTA consumes
# against a SAIF activity file) and a complete LEF. Enables a drop-in
# behavioral-memory flow that skips synthesis + P&R entirely: the design's
# simulation Verilog is the behavioral model, and these generated views
# are the synthesis/P&R views. Downstream orfs_macro() sees a normal pair
# of abstracts and cannot tell the difference.


def _port_pin_names(role):
    """Enumerate the firtool-convention pin list for a role.

    Returns a dict from port-id ("R0", "W0", "RW0", …) to list of
    (pin_name, direction). Port direction is "input" or "output".
    clk is always port-less.
    """
    out = {}
    for i in range(role.nR):
        out[f"R{i}"] = [
            (f"R{i}_addr", "input", True),
            (f"R{i}_en", "input", False),
            (f"R{i}_data", "output", True),
            (f"R{i}_clk", "input", False),
        ]
    for i in range(role.nW):
        out[f"W{i}"] = [
            (f"W{i}_addr", "input", True),
            (f"W{i}_en", "input", False),
            (f"W{i}_mask", "input", True),
            (f"W{i}_data", "input", True),
            (f"W{i}_clk", "input", False),
        ]
    for i in range(role.nRW):
        out[f"RW{i}"] = [
            (f"RW{i}_addr", "input", True),
            (f"RW{i}_en", "input", False),
            (f"RW{i}_wmode", "input", False),
            (f"RW{i}_wmask", "input", True),
            (f"RW{i}_wdata", "input", True),
            (f"RW{i}_rdata", "output", True),
            (f"RW{i}_clk", "input", False),
        ]
    return out


def _addr_bits(rows):
    b = 1
    while (1 << b) < max(rows, 2):
        b += 1
    return b


def generate_lib(role, tech_nm=DEFAULT_TECH_NM):
    """Return Liberty text for the role, synthesized from scratch.

    Output includes:
      - library header at the given tech_nm (picosecond timing, femtofarad
        capacitance, microwatt leakage).
      - type() blocks for each addr bus and each data bus.
      - cell() with memory() group, all pins, clk-to-data timing arcs,
        address/data setup/hold arcs, and internal_power() groups
        (one per clock edge) that wire up to OpenSTA SAIF-based power.
    """
    bucket, _ = predict_idiomatic(role, tech_nm=tech_nm)
    if bucket is None:
        raise ValueError(f"cannot generate .lib for non-memory role {role}")

    name = role.cell_name or role.library_name or f"mem_{role.rows}x{role.bits}"
    addr_w = _addr_bits(role.rows)
    data_w = role.bits

    clk_period = bucket["clk_period_min_ps"] / 1000.0  # ns
    access_ns = bucket["access_time_ps"] / 1000.0
    setup_ns = bucket["setup_ps"] / 1000.0
    hold_ns = bucket["hold_ps"] / 1000.0
    trans_ns = bucket["transition_ps"] / 1000.0
    post_cts_ck_ns = bucket["post_cts_ck_insertion_ps"] / 1000.0
    area = bucket.get("width_um", 10.0) * bucket.get("height_um", 10.0)
    leak_uw = bucket["leakage_pw"] * 1e-6  # pW → µW for Liberty default units
    read_e = bucket["read_energy_fj"]   # fJ per edge; Liberty power unit is derived from voltage/current units
    write_e = bucket["write_energy_fj"]

    lines = []
    a = lines.append
    a(f"library({name}) {{")
    a('  technology (cmos);')
    a('  delay_model : table_lookup;')
    a('  time_unit : "1ns";')
    a('  voltage_unit : "1V";')
    a('  current_unit : "1uA";')
    a('  leakage_power_unit : "1pW";')
    a('  capacitive_load_unit (1, ff);')
    a('  pulling_resistance_unit : "1kohm";')
    a('  nom_process : 1.0;')
    a('  nom_voltage : 0.70;')
    a('  nom_temperature : 25.0;')
    a('  operating_conditions(typ) { process : 1; temperature : 25; '
      'voltage : 0.70; tree_type : balanced_tree; }')
    a('  default_operating_conditions : typ;')
    a(f'  default_cell_leakage_power : {leak_uw:.6g};')
    a(f'  default_max_transition : {trans_ns * 4:.6g};')
    # Minimal 1-D LU templates so OpenSTA accepts the file.
    a('  lu_table_template(scalar) { variable_1 : input_net_transition; index_1("1000"); }')

    if role.kind == "sram":
        for port in _port_pin_names(role).values():
            for pn, _, is_bus in port:
                if pn.endswith(("_addr",)):
                    a(f'  type({name}_ADDR_{pn}) {{ base_type : array; data_type : bit; '
                      f'bit_width : {addr_w}; bit_from : {addr_w - 1}; bit_to : 0; downto : true; }}')
                elif pn.endswith(("_data", "_rdata", "_wdata", "_mask", "_wmask")):
                    a(f'  type({name}_DATA_{pn}) {{ base_type : array; data_type : bit; '
                      f'bit_width : {data_w}; bit_from : {data_w - 1}; bit_to : 0; downto : true; }}')

    a(f'  cell({name}) {{')
    a(f'    area : {area:.6g};')
    a(f'    interface_timing : true;')
    if role.kind == "sram":
        a('    memory() {')
        a(f'      type : ram;')
        a(f'      address_width : {addr_w};')
        a(f'      word_width : {data_w};')
        a('    }')

    # Unified clk pin — used by all ports in our firtool-style memories.
    a('    pin(clk) {')
    a('      direction : input;')
    a('      clock : true;')
    a(f'      capacitance : {2.0:.6g};')
    a(f'      min_period : {clk_period:.6g};')
    a('      internal_power() {')
    a('        when : "1";')
    # Per-edge total internal energy: weight by (read + write) average access.
    # SAIF activity on clk multiplied by this number gives OpenSTA the
    # dynamic-power estimate for a read-or-write per cycle at this pin.
    avg_edge_fj = (read_e + write_e) / 2.0
    a(f'        rise_power(scalar) {{ values ("{avg_edge_fj:.6g}") }}')
    a(f'        fall_power(scalar) {{ values ("{avg_edge_fj:.6g}") }}')
    a('      }')
    a(f'      timing() {{ timing_type : min_clock_tree_path; '
      f'cell_rise(scalar) {{ values ("{post_cts_ck_ns:.6g}") }} '
      f'cell_fall(scalar) {{ values ("{post_cts_ck_ns:.6g}") }} }}')
    a(f'      timing() {{ timing_type : max_clock_tree_path; '
      f'cell_rise(scalar) {{ values ("{post_cts_ck_ns:.6g}") }} '
      f'cell_fall(scalar) {{ values ("{post_cts_ck_ns:.6g}") }} }}')
    a('    }')

    # Per-port pins + timing arcs.
    for port_id, port_pins in _port_pin_names(role).items():
        for pn, direction, is_bus in port_pins:
            if pn == f"{port_id}_clk":
                # Modeled through the main clk pin; skip.
                continue
            if is_bus and role.kind == "sram":
                a(f'    bus({pn}) {{')
                a(f'      bus_type : {name}_{"ADDR" if pn.endswith("_addr") else "DATA"}_{pn};')
            else:
                a(f'    pin({pn}) {{')
            a(f'      direction : {direction};')
            a(f'      capacitance : {1.0:.6g};')
            if direction == "output":
                # Clk → data access arc.
                a('      timing() {')
                a('        related_pin : "clk";')
                a('        timing_type : rising_edge;')
                a(f'        cell_rise(scalar) {{ values ("{access_ns:.6g}") }}')
                a(f'        cell_fall(scalar) {{ values ("{access_ns:.6g}") }}')
                a(f'        rise_transition(scalar) {{ values ("{trans_ns:.6g}") }}')
                a(f'        fall_transition(scalar) {{ values ("{trans_ns:.6g}") }}')
                a('      }')
            else:
                # Data/addr/en → clk setup/hold.
                a('      timing() {')
                a('        related_pin : "clk";')
                a('        timing_type : setup_rising;')
                a(f'        rise_constraint(scalar) {{ values ("{setup_ns:.6g}") }}')
                a(f'        fall_constraint(scalar) {{ values ("{setup_ns:.6g}") }}')
                a('      }')
                a('      timing() {')
                a('        related_pin : "clk";')
                a('        timing_type : hold_rising;')
                a(f'        rise_constraint(scalar) {{ values ("{hold_ns:.6g}") }}')
                a(f'        fall_constraint(scalar) {{ values ("{hold_ns:.6g}") }}')
                a('      }')
                # Per-pin switching-power contribution — OpenSTA integrates
                # these with SAIF toggle counts to get dynamic power.
                per_pin_fj = (read_e if "data" in pn or "rdata" in pn
                              else read_e / 4.0)
                a('      internal_power() {')
                a('        related_pin : "clk";')
                a('        when : "1";')
                a(f'        rise_power(scalar) {{ values ("{per_pin_fj:.6g}") }}')
                a(f'        fall_power(scalar) {{ values ("{per_pin_fj:.6g}") }}')
                a('      }')
            a(f'      {"}}" if is_bus and role.kind == "sram" else "}"}')
        # nothing to close per port

    a(f'  }}')  # close cell
    a('}')       # close library
    return "\n".join(lines) + "\n"


def generate_lef(role, tech_nm=DEFAULT_TECH_NM):
    """Return LEF text for the role, synthesized from scratch.

    Outline from the fitted area model; pin layout from the idiomatic
    ASAP7 convention (addr/ctrl left, data-out right, clk top) already
    implemented in rewrite_lef(). For non-SRAM roles (flop-memory
    becomes a standard-cell placement rather than a macro), returns a
    null LEF so the downstream flow is informed the macro has no
    outline — caller decides whether to skip or flatten.
    """
    bucket, _ = predict_idiomatic(role, tech_nm=tech_nm)
    if bucket is None or "width_um" not in bucket:
        return ""
    name = role.cell_name or role.library_name or f"mem_{role.rows}x{role.bits}"
    # Build a stub LEF with just the name and a placeholder outline, then
    # let rewrite_lef() do the real pin placement from our known pin set.
    stub = [f"VERSION 5.8 ;",
            f"BUSBITCHARS \"[]\" ;",
            f"DIVIDERCHAR \"/\" ;",
            f"",
            f"MACRO {name}",
            f"  CLASS BLOCK ;",
            f"  ORIGIN 0 0 ;",
            f"  SIZE 1 BY 1 ;"]
    for port in _port_pin_names(role).values():
        for pn, direction, _ in port:
            if pn.endswith("_clk"):
                continue
            stub.append(f"  PIN {pn}")
            stub.append(f"    DIRECTION {'OUTPUT' if direction == 'output' else 'INPUT'} ;")
            stub.append(f"    PORT LAYER M4 ; RECT 0 0 0.1 0.1 ; END")
            stub.append(f"  END {pn}")
    stub.append(f"  PIN clk")
    stub.append(f"    DIRECTION INPUT ;")
    stub.append(f"    USE CLOCK ;")
    stub.append(f"    PORT LAYER M5 ; RECT 0 0 0.1 0.1 ; END")
    stub.append(f"  END clk")
    stub.append(f"END {name}")
    stub.append("")
    stub.append("END LIBRARY")
    return rewrite_lef("\n".join(stub) + "\n", role, bucket)


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Verilog-directory scanner: find every memory module in one or more .sv/.v
# files and classify each by shape + port set. Enables the behavioral-memory
# flow (see behavioral_macros.bzl): point at a design's Verilog, get back
# an orfs_macro() per memory module — no synthesis, no P&R, no ORFS run.
# ---------------------------------------------------------------------------

_VERILOG_MODULE_HEADER_RE = re.compile(r"^\s*module\s+(\w+)\b", re.MULTILINE)


def scan_verilog_for_memories(text):
    """Return {module_name: MemoryRole} for every memory module in `text`.

    A module is a "memory" if it parses as kind=sram or kind=flop_memory
    under classify(). Non-memory modules are skipped silently. Works on
    firtool-generated SV (the common Chisel output) because the pin-name
    conventions match classify()'s layer 2.

    The returned roles carry rows/bits/nR/nW/nRW inferred directly from
    the module header + port list — no `.lib` needed.
    """
    out = {}
    # Split the text into per-module bodies using module header positions.
    headers = list(_VERILOG_MODULE_HEADER_RE.finditer(text))
    for i, m in enumerate(headers):
        start = m.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end]
        name = m.group(1)
        # Build a minimal Liberty-shaped "cell(name) { …body… }" string so
        # classify() can reuse its pin regex without a real .lib. The
        # pin(NAME) / bus(NAME) captures inside classify() match here
        # if we rewrite `input [N:0] R0_addr` → emit a synthetic cell.
        pins = _extract_verilog_pins(body)
        if not pins:
            continue
        role = _classify_verilog_pins(name, pins)
        if role.kind in ("sram", "flop_memory"):
            out[name] = role
    return out


def scan_verilog_files(paths):
    """Aggregate scan_verilog_for_memories across multiple files/folders."""
    out = {}
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for sub in p.rglob("*.sv"):
                out.update(scan_verilog_for_memories(sub.read_text()))
            for sub in p.rglob("*.v"):
                out.update(scan_verilog_for_memories(sub.read_text()))
        else:
            out.update(scan_verilog_for_memories(p.read_text()))
    return out


_VERILOG_PORT_RE = re.compile(
    r"\b(input|output|inout)\b\s*(\[[^\]]+\])?\s*(\w+)\s*[,;)]"
)
_VERILOG_BUS_WIDTH_RE = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")


def _extract_verilog_pins(body):
    """Return list of (name, direction, width_bits) for each port declaration."""
    out = []
    for m in _VERILOG_PORT_RE.finditer(body):
        direction, bracket, name = m.group(1), m.group(2), m.group(3)
        width = 1
        if bracket:
            bm = _VERILOG_BUS_WIDTH_RE.search(bracket)
            if bm:
                width = abs(int(bm.group(1)) - int(bm.group(2))) + 1
        out.append((name, direction, width))
    return out


def _classify_verilog_pins(module_name, pins):
    """Build a MemoryRole from a list of (pin_name, direction, width)."""
    role = MemoryRole(kind="non_memory", library_name=module_name,
                     cell_name=module_name)
    # Count firtool-style R*/W*/RW* port groups, pull width from _addr/_data.
    seen = {"R": set(), "W": set(), "RW": set()}
    addr_bits = 0
    data_bits = 0
    for pn, _dir, width in pins:
        m = _FIRTOOL_PIN_RE.match(pn)
        if not m:
            continue
        kind, num, tail = m.group(1), m.group(2), m.group(3)
        seen[kind].add(num)
        if tail == "addr":
            addr_bits = max(addr_bits, width)
        elif tail in ("data", "rdata", "wdata"):
            data_bits = max(data_bits, width)
    if any(seen.values()):
        role.kind = "sram"
        role.nR = len(seen["R"])
        role.nW = len(seen["W"])
        role.nRW = len(seen["RW"])
        role.rows = (1 << addr_bits) if addr_bits else 0
        role.bits = data_bits
    else:
        # Fall back to name-suffix pattern for flop memories.
        dims = _dims_from_name(module_name)
        if dims:
            role.kind = "flop_memory"
            role.rows, role.bits = dims
    return role


def scale_reference(
    *,
    lib_post_cts_text,
    lib_pre_layout_text=None,
    lef_text,
    timing_scale_override=None,
    emit_pre_layout=False,
):
    """Return (scaled_post_cts_text, scaled_pre_layout_text_or_None, scaled_lef_text, role, bucket, warning).

    Single-input mode (place-stage macros): when lib_pre_layout_text is None
    but emit_pre_layout is True, the scaler synthesizes the pre-layout output
    from lib_post_cts_text by rewriting the clock-insertion arcs to the
    idiomatic pre-layout value (0 ps). This is correct because
    scale_reference() overwrites min/max_clock_tree_path with absolute values
    from the idiomatic table regardless of the input's values — the input
    ck-insertion arcs are not load-bearing. In practice this is the case
    when the source macro's orfs_flow uses abstract_stage = "place"
    (bazel-orfs doesn't auto-emit a pre_layout sibling for those;
    see bazel-orfs/private/flow.bzl _emit_pre_layout_abstract).

    Raises ValueError if two .libs are supplied and disagree about
    library/cell name.
    """
    role = classify(lib_post_cts_text)
    bucket, warning = lookup_idiomatic(role)

    if lib_pre_layout_text is not None:
        pre_role = classify(lib_pre_layout_text)
        if pre_role.library_name != role.library_name:
            raise ValueError(
                f"library name mismatch: post-CTS='{role.library_name}' vs "
                f"pre-layout='{pre_role.library_name}'"
            )

    timing_scale = (
        timing_scale_override
        if timing_scale_override is not None
        else compute_timing_scale(role, bucket, lib_post_cts_text)
    )

    post_ck = bucket["post_cts_ck_insertion_ps"] if bucket else None
    pre_ck = bucket["pre_layout_ck_insertion_ps"] if bucket else None

    scaled_post = scale_lib_text(
        lib_post_cts_text,
        timing_scale=timing_scale,
        ck_insertion_ps=post_ck,
    )

    pre_source = lib_pre_layout_text
    if pre_source is None and emit_pre_layout:
        pre_source = lib_post_cts_text
    scaled_pre = (
        scale_lib_text(
            pre_source,
            timing_scale=timing_scale,
            ck_insertion_ps=pre_ck,
        )
        if pre_source is not None
        else None
    )
    scaled_lef = rewrite_lef(lef_text, role, bucket)
    return scaled_post, scaled_pre, scaled_lef, role, bucket, warning


def _log_role(role, bucket, warning):
    parts = [
        f"role={role.kind}",
        f"library={role.library_name}",
        f"rows={role.rows}",
        f"bits={role.bits}",
        f"nR={role.nR}",
        f"nW={role.nW}",
        f"nRW={role.nRW}",
        f"ports_key={role.ports_key}",
    ]
    if bucket:
        parts.append(f"bucket_w={bucket.get('width_um', 'n/a')}")
        parts.append(f"bucket_h={bucket.get('height_um', 'n/a')}")
    if warning:
        parts.append(f"warning={warning!r}")
    print("memory_macro_scaler: " + " ".join(parts), file=sys.stderr)


def generate_abstracts_from_verilog(
    *,
    verilog_paths,
    out_dir,
    module_filter=None,
    tech_nm=DEFAULT_TECH_NM,
):
    """Generate .lib + .lef pairs for every memory module found in verilog_paths.

    One (<module>.lib, <module>_pre_layout.lib, <module>.lef) trio per
    detected memory module is written into out_dir. Returns the dict of
    {module_name: role}. Skips non-memory modules.

    This is the fast path: O(milliseconds) per macro, no ORFS runs.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    roles = scan_verilog_files(verilog_paths)
    if module_filter is not None:
        roles = {n: r for n, r in roles.items() if n in module_filter}
    for name, role in roles.items():
        lib_text = generate_lib(role, tech_nm=tech_nm)
        # Pre-layout = ideal-clock version of the same .lib (ck_insertion=0).
        pre_layout_text = scale_lib_text(lib_text, timing_scale=1.0,
                                         ck_insertion_ps=0.0)
        lef_text = generate_lef(role, tech_nm=tech_nm)
        (out_dir / f"{name}.lib").write_text(lib_text)
        (out_dir / f"{name}_pre_layout.lib").write_text(pre_layout_text)
        (out_dir / f"{name}.lef").write_text(lef_text)
    return roles


def main(argv=None):
    """Flat CLI, mode picked by which inputs are supplied.

    Three usage shapes:

      scale an existing dual characterization (one or two .lib + one .lef):
        --in-lib-post-cts A.lib [--in-lib-pre-layout B.lib] --in-lef A.lef
        --out-lib-post-cts X.lib --out-lib-pre-layout Y.lib --out-lef X.lef

      generate abstracts from Verilog (the "behavioral-memory" flow):
        --verilog path/ [--verilog file.sv …] --out-dir DIR
        [--module NAME …] [--tech-nm N]
    """
    p = argparse.ArgumentParser(description=__doc__)
    # Scaling-mode inputs/outputs (all optional at arg-parse time).
    p.add_argument("--in-lib-post-cts", type=Path, default=None)
    p.add_argument("--in-lib-pre-layout", type=Path, default=None)
    p.add_argument("--in-lef", type=Path, default=None)
    p.add_argument("--out-lib-post-cts", type=Path, default=None)
    p.add_argument("--out-lib-pre-layout", type=Path, default=None)
    p.add_argument("--out-lef", type=Path, default=None)
    p.add_argument("--timing-scale", type=float, default=None,
                   help="Override the computed data-path timing scale.")

    # Verilog-mode inputs.
    p.add_argument("--verilog", action="append", default=None, type=Path,
                   help="Path to a .sv/.v file or a directory tree; "
                        "repeat for multiple sources. Triggers behavioral-"
                        "memory mode.")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="Output directory for behavioral-memory mode.")
    p.add_argument("--module", action="append", default=None,
                   help="Only emit this module name (repeatable).")
    p.add_argument("--tech-nm", type=int, default=DEFAULT_TECH_NM)

    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.verilog:
        if args.out_dir is None:
            p.error("--out-dir is required with --verilog")
        return _main_from_verilog(args)
    if args.in_lib_post_cts is None or args.in_lef is None or args.out_lib_post_cts is None or args.out_lef is None:
        p.error("scaling mode requires --in-lib-post-cts, --in-lef, "
                "--out-lib-post-cts, --out-lef")
    return _main_scale(p, args)


def _main_from_verilog(args):
    roles = generate_abstracts_from_verilog(
        verilog_paths=args.verilog,
        out_dir=args.out_dir,
        module_filter=set(args.module) if args.module else None,
        tech_nm=args.tech_nm,
    )
    print(
        f"memory_macro_scaler: wrote {len(roles)} macro abstract(s) to "
        f"{args.out_dir} (tech_nm={args.tech_nm})",
        file=sys.stderr,
    )
    for name, role in roles.items():
        _log_role(role, None, None)
        print(f"  {name}: {role.kind} rows={role.rows} bits={role.bits} "
              f"ports={role.ports_key}", file=sys.stderr)
    return 0


def _main_scale(p, args):
    """Legacy path — original 'scale an existing reference' entry point.

    Preserved so older callers (and the scale_macro.bzl genrule) don't
    need an argv prefix.
    """
    post_text = args.in_lib_post_cts.read_text()
    pre_text = args.in_lib_pre_layout.read_text() if args.in_lib_pre_layout else None
    lef_text = args.in_lef.read_text()

    want_pre_layout_out = args.out_lib_pre_layout is not None
    scaled_post, scaled_pre, scaled_lef, role, bucket, warning = scale_reference(
        lib_post_cts_text=post_text,
        lib_pre_layout_text=pre_text,
        lef_text=lef_text,
        timing_scale_override=args.timing_scale,
        emit_pre_layout=want_pre_layout_out,
    )
    _log_role(role, bucket, warning)

    if args.dry_run:
        return 0

    args.out_lib_post_cts.write_text(scaled_post)
    if scaled_pre is not None:
        args.out_lib_pre_layout.write_text(scaled_pre)
    args.out_lef.write_text(scaled_lef)
    return 0


if __name__ == "__main__":
    sys.exit(main())
