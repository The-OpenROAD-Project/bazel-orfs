"""Sweep shape table for the ASAP7 FF-memory characterization run.

Kept in one place so the generator (generate_sweep.py), the Bazel-level
multi-flow wiring (characterization/BUILD), and anyone reading the sweep
results all see the same (rows, bits, ports, write_mask_bits) list. Edit
here; everything downstream follows.

Literature-driven selection
---------------------------
Shapes span the knees of scaling curves identified in the following
references, so the fit has data across the regimes that matter:

- OpenRAM paper (Guthaus et al., ICCAD 2016) shows SRAM area scales
  primarily with bit-count and secondarily with row count (decoder
  growth). Covers 64..2048 rows in powers of two.
- DFFRAM (AUCOHL/DFFRAM) publishes FF-memory area at 32..2048 rows
  fixed at 32 bits with byte-write. We mirror that grid so the ASAP7
  fit can be cross-checked against sky130 at the same shapes.
- OpenROAD RegFileStudy (The-OpenROAD-Project/RegFileStudy) varies port
  count at fixed rows/bits to isolate port cost. We keep 64x32 fixed
  and sweep 1RW / 1R1W / 2R1W / 3R1W / 4R1W to capture port scaling
  in 7 nm.
- CACTI (Thoziyoor et al., "CACTI 5.1", HPL-2008-20) motivates
  including a separate bit-line-length sweep (128..512 rows at 64
  bits) because per-row bit-line RC dominates access time above ~256
  rows.

The sweep is tagged manual so it does not slow down CI. Each entry
becomes one orfs_flow target; results are harvested into
asap7_sweep.yaml.
"""

SWEEP_SHAPES = [
    # --- DFFRAM-grid cross-check at 32 bits, byte-write ---
    dict(rows=32, bits=32, ports_key="1RW", write_mask_bits=8),
    dict(rows=128, bits=32, ports_key="1RW", write_mask_bits=8),
    dict(rows=256, bits=32, ports_key="1RW", write_mask_bits=8),
    dict(rows=512, bits=32, ports_key="1RW", write_mask_bits=8),
    dict(rows=1024, bits=32, ports_key="1RW", write_mask_bits=8),
    # --- Width sweep at fixed 128 rows, 1RW ---
    dict(rows=128, bits=8, ports_key="1RW", write_mask_bits=0),
    dict(rows=128, bits=16, ports_key="1RW", write_mask_bits=0),
    dict(rows=128, bits=32, ports_key="1RW", write_mask_bits=0),
    dict(rows=128, bits=64, ports_key="1RW", write_mask_bits=0),
    dict(rows=128, bits=128, ports_key="1RW", write_mask_bits=0),
    # --- Port sweep at fixed 64x32 (RegFileStudy pattern) ---
    dict(rows=64, bits=32, ports_key="1RW", write_mask_bits=0),
    dict(rows=64, bits=32, ports_key="1R1W", write_mask_bits=0),
    dict(rows=64, bits=32, ports_key="2R1W", write_mask_bits=0),
    dict(rows=64, bits=32, ports_key="3R1W", write_mask_bits=0),
    dict(rows=64, bits=32, ports_key="4R1W", write_mask_bits=0),
    # --- Bit-line-length sweep at 64 bits, 1RW (CACTI motivation) ---
    dict(rows=128, bits=64, ports_key="1RW", write_mask_bits=0),
    dict(rows=256, bits=64, ports_key="1RW", write_mask_bits=0),
    dict(rows=512, bits=64, ports_key="1RW", write_mask_bits=0),
    # --- Masked-write study at a modest size ---
    dict(rows=128, bits=32, ports_key="1RW", write_mask_bits=1),  # bit-write
    dict(rows=128, bits=32, ports_key="1RW", write_mask_bits=4),  # nibble
    dict(rows=128, bits=32, ports_key="1RW", write_mask_bits=16),  # halfword
]
