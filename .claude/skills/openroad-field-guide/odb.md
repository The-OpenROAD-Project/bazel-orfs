# odb, parasitic estimation and extraction

Paths are in OpenROAD's `src/odb/`, `src/est/`, `src/rcx/`.

## odb

- `read_db`/`write_db` are one serial stream, no threads. On XiangShan
  stage files are gigabytes; the read is a fixed cost of every stage and
  every odb-debug session.
- What grows the database: instances and iterms; access points after
  grt's `pin_access`; guides and GRT congestion markers ([grt.md](grt.md));
  wires after drt; DRC markers; RCX segments.
- **Tcl accessors retain ~1 KB per distinct object forever**: a Tcl loop
  over every net (unit-RC calibration, RCX read-back) runs out of memory
  (bazel-orfs #966, OpenROAD #11365 closed). Walk the database in C++ or
  Python, not Tcl.
- Hierarchical `link_design` of a big parent took 7 min single-threaded
  at 20 GB, string-keyed (`ideas/xiangshan-timing.md` entry 6).
- odb has no FIXED placement status: DEF's FIXED is odb's FIRM.
- Under `read_db -hier`, STA keeps only the part of a flat name after its
  last `/`.

**Dead ends, smaller .odb** (all measured, all closed): field-major
tables (OpenROAD #11328), structure-of-arrays switch (#11352, 1.38x
smaller, 10 % less RSS, read-path complexity), an `ODB_CODEC` hook
(#11524, no dependency injection upstream), learned reordering (1.98x
but 2-4 MB/s encode, `ideas/odb-swap.md`). Do not restart schema-free
.odb compression without a cheap way to find table boundaries; measure
encode MB/s on a 100 MB case before ratio.

## est: estimate_parasitics

- `-placement`: a Steiner tree per net with per-layer average RC from
  `set_wire_rc`. Parallel over nets.
- `-global_routing`: RC from grt segments including vias. Parallel
  (OpenROAD #11569/#11599). Errors with EST-0020 on congested routes
  without `-allow_congestion`.
- Incremental: only invalidated nets; in grt mode it first reroutes them
  (see [rsz.md](rsz.md)).
- **ORFS calls `estimate_parasitics -global_routing` 4-5 times in
  `global_route.tcl`**, each a full rebuild and timer invalidation.
- Global route is the noisy end: 2 sigma 13.8 % vs 4.3 % at place over
  12 seeds. Platform resistance transfers between designs; capacitance
  misses by -25 % to +12 % (bazel-orfs #958).

## rcx: extract_parasitics

Final stage only, and only when the platform sets `RCX_RULES`.
Single-threaded. Writes RC into odb, then `write_spef`, then `read_spef`:
memory holds both. Final RCX used more memory than detailed route
(OpenROAD #11365, the Tcl retention above).
