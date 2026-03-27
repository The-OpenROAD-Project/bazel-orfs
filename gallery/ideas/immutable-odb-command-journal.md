# Immutable ODB with Command Journal

[OpenROAD #9854](https://github.com/The-OpenROAD-Project/OpenROAD/issues/9854)

## Problem

`.odb` files contain design state but no record of how they got there. The
commands that created them are scattered across log files, Tcl scripts, and
environment variables. This makes debugging, reproduction, and historical
analysis unnecessarily hard:

- **Debugging**: DRT-0073 in routing → root cause is `place_pin` in floorplan,
  but no breadcrumbs connect them
- **Reproduction**: bug reports require manually assembling .odb + scripts +
  env vars into a `bug.tcl`
- **KPI mining**: plotting WNS over 50 experiments requires rebuilding each
  (~23 hours) instead of reading a property (< 1 minute)

## Prior Art

### Commercial EDA — command logs as sidecar files

Every major EDA tool records commands, but always as **external files**, never
embedded in the design database:

| Tool | Mechanism | Limitation |
|------|-----------|------------|
| **Xilinx Vivado** | `vivado.jou` — auto-written Tcl journal of every command ([AMD docs](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/Tcl-Journal-Files)) | Separate file, not embedded in design |
| **Synopsys ICC2** | NDM block labels (`save_block -label placed`) — named design snapshots | State versioning only, no command history |
| **Synopsys DC** | `write_script` — reconstructs Tcl to recreate current state | Reverse-engineered, not actual commands |
| **Cadence Innovus** | `innovus.cmd` / `innovus.log` — session command log | External file, easily separated from design |
| **Cadence Virtuoso** | Undo history during editing | **Cleared on save** — design carries no history |

**Key gap**: No commercial tool makes the design artifact **self-describing**.
The journal is always a sidecar that gets separated from the data it describes.

### Scientific computing — provenance systems

The idea maps directly to well-studied provenance patterns:

- **W3C PROV standard** ([W3C TR](https://www.w3.org/TR/prov-dm/)) — formal
  model: Entity (`.odb`), Activity (Tcl commands), Agent (OpenROAD version).
  The ODB journal would be a natural PROV record.
- **VisTrails** (U. Utah) — pioneered **change-based provenance**, recording
  a version tree of workflow modifications. Analogous to tracking how an ODB
  evolved through command changes.
- **noWorkflow** (VLDB 2017, [paper](https://dl.acm.org/doi/10.14778/3137765.3137789))
  — captures Python provenance **non-intrusively** via AST/profiling hooks.
  Directly analogous to using Tcl `trace` for zero-instrumentation capture.
- **Sumatra** — tracks computational experiments by recording code versions,
  parameters, environment, and outputs. Similar to recording commands + input
  hashes in ODB.
- **PASS** (Provenance-Aware Storage System) — OS-level provenance. Cautionary
  tale: generates "overwhelming amounts of data." Validates the ODB proposal's
  ~10 KB target as well-calibrated.

Surveys: Freire et al., "Provenance for Computational Tasks" (IEEE CISE 2008,
[paper](https://dl.acm.org/doi/10.1109/MCSE.2008.79)); Pimentel et al.,
"Provenance Analytics" (ACM Computing Surveys 2019,
[paper](https://dl.acm.org/doi/10.1145/3184900)).

### CS patterns — event sourcing

The proposal is **event sourcing** applied to chip design:

- **Event sourcing** — store an immutable, append-only log of state-changing
  events; derive current state by replay. The `.odb` carries both current state
  and the event log (Tcl commands) that produced it.
- **CQRS** — command side (journal) vs query side (`report_journal`). The ODB
  state itself is a materialized view.
- **Write-ahead logging** — databases record changes before applying them for
  crash recovery. The journal enables point-in-time replay.
- **Spark lineage** — tracks transformation DAGs for resilient recomputation.
  The `-replay <stage>` concept follows this pattern.

### EDA-specific academic work

- **mflowgen** (Stanford, DAC 2022,
  [paper](https://dl.acm.org/doi/10.1145/3489517.3530633)) — modular VLSI flow
  generator with sandboxed nodes and tracked inputs/outputs. Operates at the
  **flow level** (which steps ran), not **command level** (what happened inside
  each step). The ODB journal provides intra-step provenance that complements
  mflowgen.
- **Hammer** (UC Berkeley, DAC 2022,
  [paper](https://dspace.mit.edu/bitstream/handle/1721.1/146410/3489517.3530672.pdf))
  — VLSI flow framework with YAML/JSON intermediate representation. Captures
  *intent* (the IR) but not *what actually happened* (actual tool commands).
- **Kahng et al.** (UCSD, ICCAD 2024,
  [paper](https://vlsicad.ucsd.edu/Publications/Conferences/412/c412.pdf)) —
  "Strengthening Foundations of IC Physical Design" addresses reproducibility
  in PD and ML-EDA research with improved baselines and benchmarks.
- **Early VLSI DB work** — DAC 1982
  ([paper](https://dl.acm.org/doi/10.5555/800263.809218)) proposed database
  approaches for VLSI design data; DAC 1988
  ([paper](https://dl.acm.org/doi/10.5555/285730.285772)) presented version
  management for hierarchical designs.

### Design data management — file-level versioning

- **ClioSoft SOS** — leading design data management for IC design. Centralized
  model with edit locks (Git doesn't work for large binary design files).
  Operates at **file level**, not command level.
  ([ClioSoft blog](https://www.cliosoft.com/2022/01/05/git-r-dont-for-hardware-design/))
- **IC Manage / Perforce** — similar file-level design data management.
- **OpenAccess (Si2)** — open standard IC design database. Multi-user access
  with locking but **no** command journaling or provenance.
  ([Si2](https://si2.org/openaccess-coalition/))
- **MLflow / DVC analogy** — ML experiment tracking records parameters,
  metrics, and artifacts per run. The ODB journal serves the same role but
  embedded in the artifact itself, not in a separate tracking server.

## What's Novel

| Aspect | State of the art | This proposal |
|--------|-----------------|---------------|
| Command logs | Sidecar files (.jou, .cmd, .log) | **Embedded in .odb** |
| Design versioning | File-level (ClioSoft, Git) | **Command-level journal** |
| State snapshots | ICC2 NDM labels | **Journal + replay** |
| Provenance | External systems (mflowgen, Hammer) | **Self-contained in artifact** |
| Reproducibility | Manually assemble scripts + data | **`report_journal` → bug.tcl** |

The key innovation is making the design artifact **self-describing** — carrying
its own complete provenance — which no commercial or open-source EDA tool
currently does. This combines Vivado's command journaling (but embedded),
ICC2's design versioning (but with command history), and event sourcing (but
for chip design).

## Idea

Every `.odb` carries a **Tcl command journal** — a text log of every OpenROAD
command executed to produce it. Stored as `dbStringProperty` on `dbBlock`
(zero schema change) or a new `dbBlock` field (schema bump).

Key capabilities:
- `report_journal` — inspect what commands created this .odb
- `report_journal place_pin` — filter for specific commands
- `-replay <stage>` — load checkpoint .odb and replay to any stage
- Enhanced error messages that auto-grep the journal for relevant commands
- SHA256 hashes of input files (LEF, LIB, SDC) for provenance tracking

~50 lines of Tcl (trace interception) + ~10 lines of C++ (dbBlock API).
~10 KB overhead per .odb (~100 commands per run).

## Impact

- **Debugging**: error messages include the command that caused the problem
- **Reproduction**: `report_journal` produces a self-contained bug.tcl
- **AI assistants**: Claude reads the journal instead of guessing the flow
- **KPI dashboards**: instant metric queries across experiments (< 1s vs hours)
- **Disk savings**: store one checkpoint .odb + replay, not every intermediate

## Effort

Medium — phased implementation:
1. Prototype with `dbStringProperty` (days)
2. Replay from checkpoint (weeks)
3. Error context from journal (weeks)
4. Metrics embedding (days)
